import os
import redis
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner, WorkerRunner

TARGET_PATH = os.environ.get("TARGET_PATH", "/health/live")   # 兜底默认，运行时会被 set_path 覆盖
ACTIVE_RUN_KEY = "locust:active_run"


def _decode(value):
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else str(value)


def _on_set_path(environment, msg, **kwargs):
    global TARGET_PATH
    TARGET_PATH = msg.data


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
    _install_owned_deadlines(environment)
    if isinstance(environment.runner, WorkerRunner):
        environment.runner.register_message("set_path", _on_set_path)


@events.test_start.add_listener
def _on_test_start(environment, **kwargs):
    if isinstance(environment.runner, MasterRunner):
        r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
        run_id = _decode(r.get(ACTIVE_RUN_KEY))
        if run_id:
            path = _decode(r.get(f"locust:target_path:{run_id}"))
            if path:
                environment.runner.send_message("set_path", path)


class WebsiteUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def hit(self):
        self.client.get(TARGET_PATH)
