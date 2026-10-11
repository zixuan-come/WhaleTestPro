import os
import json
import time
from uuid import uuid4
import redis
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner, WorkerRunner
from locust.exception import StopUser
from app.core.perf_plan import execute_iteration
from app.schemas.perf_plan import PerfLoadConfig

TARGET_PATH = os.environ.get("TARGET_PATH", "/health/live")   # 兜底默认，运行时会被 set_path 覆盖
ACTIVE_RUN_KEY = "locust:active_run"
RUN_LOCK_KEY = "locust:run_lock"
_iteration_stats = {"lease": None, "iterations": 0, "failures": 0, "configuration_failures": 0, "total_duration_ms": 0.0}
_worker_iterations = {}
_iteration_started = 0.0
_iteration_finished = None
_announced_lease = None


def _on_set_lease(environment, msg, **kwargs):
    global _announced_lease
    _announced_lease = msg.data


def _owned_plan(redis_client, default_host):
    lease = _decode(redis_client.get(RUN_LOCK_KEY))
    run_id = _decode(redis_client.get(ACTIVE_RUN_KEY))
    if not lease or not run_id or not lease.startswith(run_id + ":"):
        raise ValueError("没有有效压测租约")
    raw = _decode(redis_client.get(f"locust:target_path:{run_id}"))
    if not raw:
        raise ValueError("压测配置缺失")
    legacy = not raw.startswith("{")
    if legacy:
        host, deadline = default_host, None
        plan = PerfLoadConfig(steps=[{"path": raw}], wait_seconds=2)
    else:
        payload = json.loads(raw)
        if payload["lease"] != lease:
            raise ValueError("压测配置租约不匹配")
        host, deadline = payload["target_host"], payload["deadline"]
        plan = PerfLoadConfig.model_validate(payload["load_config"])
    if _decode(redis_client.get(RUN_LOCK_KEY)) != lease or _decode(redis_client.get(ACTIVE_RUN_KEY)) != run_id:
        raise ValueError("读取配置时压测租约发生变化")
    return lease, host, plan, deadline, legacy


def _receive_iteration_report(environment, client_id, data, **kwargs):
    report = data.get("whale_iterations")
    if report and report.get("lease") == _iteration_stats["lease"]:
        _worker_iterations[client_id] = dict(report)


def _receive_final(environment, msg, **kwargs):
    _receive_iteration_report(environment, msg.node_id, {"whale_iterations": msg.data})


def _iteration_summary(environment):
    rows = list(_worker_iterations.values()) if isinstance(environment.runner, MasterRunner) else [_iteration_stats]
    count = sum(row["iterations"] for row in rows)
    failures = sum(row["failures"] for row in rows)
    total = sum(row["total_duration_ms"] for row in rows)
    elapsed = max((_iteration_finished or time.monotonic()) - _iteration_started, 0.001)
    return {"iterations": count, "failures": failures,
            "configuration_failures": sum(row.get("configuration_failures", 0) for row in rows),
            "lease": _iteration_stats["lease"],
            "fail_ratio": failures / count if count else 0,
            "avg_duration_ms": total / count if count else 0,
            "iteration_rps": count / elapsed, "elapsed_seconds": elapsed}


def _decode(value):
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else str(value)


def _on_set_path(environment, msg, **kwargs):
    global TARGET_PATH
    TARGET_PATH = msg.data


def _install_control_auth(environment):
    web_ui = getattr(environment, "web_ui", None)
    if web_ui is None or getattr(web_ui, "_whale_control_auth_installed", False):
        return
    import hmac
    from flask import jsonify, request
    token = os.environ.get("LOCUST_CONTROL_TOKEN", "")

    @web_ui.app.before_request
    def require_internal_control_token():
        if not token:
            return jsonify(success=False, message="Locust control token is not configured"), 503
        provided = request.headers.get("X-Locust-Control-Token", "")
        if not hmac.compare_digest(provided.encode("utf-8"), token.encode("utf-8")):
            return jsonify(success=False, message="Forbidden"), 403

    web_ui._whale_control_auth_installed = True


def _install_owned_deadlines(environment):
    """Replace Locust's untracked /swarm timer with a cancellable generation."""
    web_ui = getattr(environment, "web_ui", None)
    if web_ui is None or getattr(web_ui, "_whale_deadlines_installed", False):
        return
    import gevent
    from gevent.lock import Semaphore
    from flask import jsonify, request
    from locust.util.timespan import parse_timespan

    app = web_ui.app
    lock = Semaphore()
    state = {"generation": 0, "timer": None}

    def cancel_deadline():
        state["generation"] += 1
        timer, state["timer"] = state["timer"], None
        if timer is not None:
            timer.kill(block=False)

    def deadline(generation):
        with lock:
            if state["generation"] != generation:
                return
            state["timer"] = None
            state["generation"] += 1
            if environment.runner is not None:
                environment.runner.stop()

    endpoints = {rule.rule: rule.endpoint for rule in app.url_map.iter_rules()}
    swarm_endpoint, stop_endpoint = endpoints["/swarm"], endpoints["/stop"]
    original_swarm = app.view_functions[swarm_endpoint]
    original_stop = app.view_functions[stop_endpoint]

    def swarm():
        raw_duration = request.form.get("run_time")
        duration = None
        if raw_duration:
            try:
                duration = parse_timespan(raw_duration)
                if duration <= 0:
                    raise ValueError("duration must be positive")
            except ValueError:
                return jsonify(success=False, message="Invalid run_time"), 400
        # Do not let the original handler spawn an untracked timer. The request
        # form is local to this request; all other Locust inputs remain intact.
        original_form = request.form
        form = original_form.copy()
        form.pop("run_time", None)
        request.form = form
        try:
            with lock:
                response = app.make_response(original_swarm())
                result = response.get_json(silent=True)
                if result and result.get("success"):
                    cancel_deadline()
                    if duration is not None:
                        generation = state["generation"]
                        state["timer"] = gevent.spawn_later(duration, deadline, generation)
                        result["run_time"] = duration
                        response.set_data(app.json.dumps(result))
                return response
        finally:
            request.form = original_form

    def stop():
        with lock:
            response = app.make_response(original_stop())
            result = response.get_json(silent=True)
            if result and result.get("success"):
                cancel_deadline()
            return response

    app.view_functions[swarm_endpoint] = swarm
    app.view_functions[stop_endpoint] = stop
    web_ui._whale_deadlines_installed = True


@events.init.add_listener
def _on_init(environment, **kwargs):
    _install_control_auth(environment)
    _install_owned_deadlines(environment)
    if isinstance(environment.runner, WorkerRunner):
        environment.runner.register_message("set_path", _on_set_path)
        environment.runner.register_message("set_lease", _on_set_lease)
    elif isinstance(environment.runner, MasterRunner):
        environment.runner.register_message("whale_final", _receive_final)
    web = getattr(environment, "web_ui", None)
    if web is not None and not getattr(web, "_whale_iteration_route", False):
        from flask import jsonify
        web.app.add_url_rule("/whale/iterations", "whale_iterations",
                             lambda: jsonify(_iteration_summary(environment)))
        web._whale_iteration_route = True


@events.test_start.add_listener
def _on_test_start(environment, **kwargs):
    global _iteration_started, _iteration_finished
    _iteration_stats.update(lease=_announced_lease if isinstance(environment.runner, WorkerRunner) else None,
                            iterations=0, failures=0, configuration_failures=0, total_duration_ms=0.0)
    _worker_iterations.clear()
    _iteration_started = time.monotonic()
    _iteration_finished = None
    if isinstance(environment.runner, MasterRunner):
        r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
        run_id = _decode(r.get(ACTIVE_RUN_KEY))
        _iteration_stats["lease"] = _decode(r.get(RUN_LOCK_KEY))
        if _iteration_stats["lease"]:
            # Sent synchronously before the master dispatches its spawn messages.
            environment.runner.send_message("set_lease", _iteration_stats["lease"])
        if run_id:
            path = _decode(r.get(f"locust:target_path:{run_id}"))
            if path:
                if path.startswith("{"):
                    path = json.loads(path)["load_config"]["steps"][0]["path"]
                environment.runner.send_message("set_path", path)


@events.report_to_master.add_listener
def _report_iterations(client_id, data, **kwargs):
    data["whale_iterations"] = dict(_iteration_stats)


@events.worker_report.add_listener
def _worker_report(client_id, data, **kwargs):
    # The hook does not carry Environment; only the master receives this event.
    report = data.get("whale_iterations")
    if report and report.get("lease") == _iteration_stats["lease"]:
        _worker_iterations[client_id] = dict(report)


@events.test_stop.add_listener
def _report_final_iterations(environment, **kwargs):
    global _iteration_finished
    _iteration_finished = time.monotonic()
    if isinstance(environment.runner, WorkerRunner):
        environment.runner.send_message("whale_final", dict(_iteration_stats))


class WebsiteUser(HttpUser):
    def on_start(self):
        try:
            self._redis = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
                                         socket_timeout=5, socket_connect_timeout=5)
            self._lease, self._host, self._plan, self._deadline, self._legacy = _owned_plan(self._redis, self.host)
        except Exception:
            # Fail closed: never turn a missing POST/chain plan into default GET.
            _iteration_stats["configuration_failures"] += 1
            raise StopUser() from None
        if _iteration_stats["lease"] != self._lease:
            _iteration_stats.update(lease=self._lease, iterations=0, failures=0, configuration_failures=0, total_duration_ms=0.0)
        self._vu_id = uuid4().hex
        self._iteration = 0

    def wait_time(self):
        return between(1, 3)(self) if self._legacy else self._plan.wait_seconds

    @task
    def hit(self):
        try:
            if _decode(self._redis.get(RUN_LOCK_KEY)) != self._lease:
                raise StopUser()
            if self._deadline is not None and time.time() >= self._deadline:
                raise StopUser()
        except redis.RedisError:
            raise StopUser() from None
        self._iteration += 1
        result = execute_iteration(self.client, self._host, self._plan, self._vu_id, self._iteration)
        _iteration_stats["iterations"] += 1
        _iteration_stats["failures"] += int(not result["passed"])
        _iteration_stats["total_duration_ms"] += result["duration_ms"]
