import time
import json
from html import unescape
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import redis
import requests
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core import metrics
from app.repositories import perf as perf_repo
from app.repositories import project as project_repo
from app.core.perf_history import RESULT_FIELDS, transaction_sample


RUN_LOCK_KEY = "locust:run_lock"
ACTIVE_RUN_KEY = "locust:active_run"
CONTROL_LOCK_KEY = "locust:control_lock"
RUN_LOCK_GRACE_SECONDS = 300


class PerfRunBusyError(RuntimeError):
    """Raised when the singleton Locust master is already serving another run."""


class PerfControlUnavailableError(RuntimeError):
    pass


def _control_timeout() -> float:
    # Leave headroom for connect + read timeout and the polling pause.
    return max(0.01, min(settings.REQUEST_TIMEOUT_SECONDS,
                         settings.PERF_HEARTBEAT_TIMEOUT_SECONDS / 4))


def assert_project_idle(project_id: int) -> None:
    """Called with the project admission row locked; never auto-stop a run."""
    try:
        cache = redis.from_url(settings.REDIS_URL)
        owners = [_decode_redis_value(cache.get(key)) for key in (RUN_LOCK_KEY, ACTIVE_RUN_KEY)]
    except redis.RedisError:
        raise PerfControlUnavailableError("无法检查项目压测执行锁，项目已保留，请稍后重试") from None
    if any(owner and owner.startswith(f"{project_id}:") for owner in owners):
        raise PerfRunBusyError("项目压测执行租约尚未清理，请先停止并清理后再删除")


def _control_headers() -> dict[str, str]:
    if not settings.LOCUST_CONTROL_TOKEN:
        raise PerfControlUnavailableError("压测控制凭证未配置，请配置 LOCUST_CONTROL_TOKEN")
    return {"X-Locust-Control-Token": settings.LOCUST_CONTROL_TOKEN}


def _utcnow() -> datetime:
    """Return a naive UTC datetime suitable for MySQL DATETIME columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _run_id(project_id: int, task_id: int) -> str:
    return f"{project_id}:{task_id}"


def _lease_id(run_id: str, celery_task_id: str) -> str:
    return f"{run_id}:{celery_task_id}"


def _target_path_key(run_id: str) -> str:
    return f"locust:target_path:{run_id}"


def _run_ttl(duration: int) -> int:
    return max(int(duration) + RUN_LOCK_GRACE_SECONDS, RUN_LOCK_GRACE_SECONDS)


def _decode_redis_value(value) -> str | None:
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else str(value)


def _acquire_run_lock(redis_client, run_id: str, duration: int) -> bool:
    owner = _decode_redis_value(redis_client.get(RUN_LOCK_KEY))
    ttl = _run_ttl(duration)
    if owner == run_id:
        redis_client.expire(RUN_LOCK_KEY, ttl)
        return True
    return bool(redis_client.set(RUN_LOCK_KEY, run_id, nx=True, ex=ttl))


def _refresh_run_keys(redis_client, run_id: str, duration: int) -> None:
    ttl = _run_ttl(duration)
    for key in (RUN_LOCK_KEY, ACTIVE_RUN_KEY, _target_path_key(run_id)):
        redis_client.expire(key, ttl)


def _release_run_lock(redis_client, run_id: str, lease_id: str | None = None) -> int:
    script = """
    if redis.call('get', KEYS[1]) ~= ARGV[1] then
        return 0
    end
    if redis.call('get', KEYS[2]) == ARGV[2] then
        redis.call('del', KEYS[2])
    end
    redis.call('del', KEYS[3])
    return redis.call('del', KEYS[1])
    """
    return redis_client.eval(
        script,
        3,
        RUN_LOCK_KEY,
        ACTIVE_RUN_KEY,
        _target_path_key(run_id),
        lease_id or run_id,
        run_id,
    )


@contextmanager
def _locust_control(redis_client):
    """Serialize master HTTP commands and lease release while they are in flight."""
    owner = str(uuid4())
    ttl = max(RUN_LOCK_GRACE_SECONDS, int(settings.REQUEST_TIMEOUT_SECONDS * 2) + 1)
    if not redis_client.set(CONTROL_LOCK_KEY, owner, nx=True, ex=ttl):
        raise PerfRunBusyError("Locust 控制请求正在处理")
    try:
        yield
    finally:
        redis_client.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end return 0",
            1, CONTROL_LOCK_KEY, owner,
        )


def _stop_owned_run_unlocked(redis_client, lease_id: str) -> None:
    if _decode_redis_value(redis_client.get(RUN_LOCK_KEY)) != lease_id:
        raise RuntimeError("压测执行锁已丢失，禁止停止其他任务")
    redis_client.expire(RUN_LOCK_KEY, RUN_LOCK_GRACE_SECONDS)
    requests.get(
        f"{settings.LOCUST_MASTER_URL}/stop",
        headers=_control_headers(),
        timeout=_control_timeout(),
    ).raise_for_status()


def _stop_owned_run(redis_client, lease_id: str) -> None:
    with _locust_control(redis_client):
        _stop_owned_run_unlocked(redis_client, lease_id)


def _cleanup_run(redis_client, run_id: str, lease_id: str, needs_stop: bool) -> bool:
    try:
        with _locust_control(redis_client):
            if _decode_redis_value(redis_client.get(RUN_LOCK_KEY)) != lease_id:
                return False
            # Recheck ACTIVE inside the control lock: a launch may have completed
            # after the reconciler's earlier snapshot.
            active = _decode_redis_value(redis_client.get(ACTIVE_RUN_KEY))
            redis_client.expire(RUN_LOCK_KEY, RUN_LOCK_GRACE_SECONDS)
            if needs_stop or active == run_id:
                _stop_owned_run_unlocked(redis_client, lease_id)
            _release_run_lock(redis_client, run_id, lease_id)
            return True
    except Exception:
        return False  # Reconciliation retries; never free an in-flight master.


def s_create(db: Session, perf, project_id: int):
    return perf_repo.db_create(db, perf, project_id)


def s_get(db: Session, task_id: int, project_id: int):
    s_reconcile_stale(db, project_id=project_id)
    task = perf_repo.db_get(db, task_id, project_id)
    return perf_repo.annotate_runs(db, [task])[0] if task else None


def s_list(db: Session, project_id: int):
    s_reconcile_stale(db, project_id=project_id)
    return perf_repo.annotate_runs(db, perf_repo.db_list(db, project_id))


def s_delete(db: Session, task_id: int, project_id: int):
    if project_repo.db_lock_project(db, project_id) is None:
        db.rollback()
        return None
    task = perf_repo.db_get_for_update(db, task_id, project_id)
    if task is None:
        return None
    if task.status in {"queued", "running"}:
        raise PerfRunBusyError("压测任务正在排队或运行，请先停止后再删除")
    if task.status in {"done", "failed", "cancelled"}:
        redis_client = redis.from_url(settings.REDIS_URL)
        run_id = _run_id(project_id, task_id)
        try:
            lease = _decode_redis_value(redis_client.get(RUN_LOCK_KEY))
        except redis.RedisError as exc:
            raise PerfControlUnavailableError("无法检查压测执行锁，请稍后重试") from exc
        if lease and lease.startswith(f"{run_id}:"):
            if not _cleanup_run(redis_client, run_id, lease, needs_stop=True):
                raise PerfControlUnavailableError("压测控制清理未完成，记录和执行锁已保留，请稍后重试")
    result = perf_repo.db_delete(db, task_id, project_id)
    if result is None:
        # A failed conditional DELETE can mean a concurrent state transition,
        # not a missing row. Refresh the session before distinguishing them.
        db.expire_all()
        if perf_repo.db_get(db, task_id, project_id) is not None:
            raise PerfRunBusyError("压测任务状态已变化，请刷新后重试删除")
    return result


def _control_get_json(base: str, path: str):
    """Keep control timeout, status validation and JSON decoding in one place."""
    response = requests.get(f"{base}{path}", headers=_control_headers(), timeout=_control_timeout())
    response.raise_for_status()
    return response.json()


def _validate_iterations(iteration_stats, lease_id: str):
    if iteration_stats.get("lease") != lease_id or iteration_stats.get("configuration_failures", 0):
        raise PerfControlUnavailableError("Locust 压测配置未正常加载，已停止任务")


MAX_LIVE_HISTORY_SAMPLES = 600


def _result_statistics(stats, live_rps, live_endpoint_rps, history_samples, *, allow_empty=False):
    """Pure final-stat mapping; stopped counters must not replace live RPS."""
    rps = live_rps if live_rps is not None else stats.get("total_rps")
    fail_ratio = stats.get("fail_ratio")
    aggregate = next((row for row in stats.get("stats", []) if row.get("name") == "Aggregated"), {})
    request_count = max(aggregate.get("num_requests", 0) or 0,
                        sum(row.get("num_requests", 0) or 0 for row in stats.get("stats", [])
                            if row.get("name") != "Aggregated"))
    if request_count <= 0 and not allow_empty:
        raise PerfControlUnavailableError("Locust 未产生任何请求，压测未有效执行；请检查 Worker 和目标配置")
    avg = aggregate.get("avg_response_time")
    p95 = aggregate.get("response_time_percentile_0.95", aggregate.get("95th_percentile"))
    p99 = aggregate.get("response_time_percentile_0.99", aggregate.get("99th_percentile"))
    request_stats = [
        {"name": row.get("name"), "method": row.get("method"), "num_requests": row.get("num_requests", 0), "num_failures": row.get("num_failures", 0), "rps": live_endpoint_rps.get((row.get("method"), row.get("name")), row.get("current_rps", row.get("rps"))), "avg_response_ms": row.get("avg_response_time"), "p95_response_ms": row.get("response_time_percentile_0.95", row.get("95th_percentile")), "p99_response_ms": row.get("response_time_percentile_0.99", row.get("99th_percentile"))}
        for row in stats.get("stats", []) if row.get("name") != "Aggregated"
    ]
    requests_by_endpoint = {(row["method"], row["name"]): row["num_requests"] for row in request_stats}
    error_summary = []
    for row in stats.get("errors", []):
        occurrences = row.get("occurrences", 0)
        # Locust escapes errors.name for its Web UI, but not stats.name.
        name = unescape(row["name"]) if row.get("name") is not None else None
        count = requests_by_endpoint.get((row.get("method"), name), 0)
        error_summary.append({
            "name": name, "method": row.get("method"),
            "error_count": occurrences,
            "error_rate": occurrences / count if count else None,
            "message": row.get("error") or row.get("last_error"),
        })
    return {
        "rps": rps, "avg_response_ms": avg, "p95_response_ms": p95,
        "p99_response_ms": p99, "fail_ratio": fail_ratio,
        "request_stats": request_stats or None, "error_summary": error_summary or None,
        "history_samples": history_samples or None,
    }


def s_run(db: Session, task_id: int, project_id: int, celery_task_id: str | None = None):
    # Every worker write is fenced by its execution ID, including late writes
    # after a cancelled run has been cleared or this definition has run again.
    previous = db.info.get("perf_execution")
    if celery_task_id:
        db.info["perf_execution"] = (task_id, project_id, celery_task_id)
    try:
        return _run(db, task_id, project_id, celery_task_id)
    finally:
        if previous is None:
            db.info.pop("perf_execution", None)
        else:
            db.info["perf_execution"] = previous


def _run(
    db: Session,
    task_id: int,
    project_id: int,
    celery_task_id: str | None = None,
):
    # Worker adoption is admission too: it must not recreate a lease from an
    # old queued snapshot after cancellation/project cascade has won the race.
    if project_repo.db_lock_project(db, project_id) is None:
        db.rollback()
        return None
    task = perf_repo.db_get_for_update(db, task_id, project_id)
    if task is None:
        db.rollback()
        return None
    run_id = _run_id(project_id, task_id)
    message_id = celery_task_id or getattr(task, "celery_task_id", None) or "legacy"
    lease_id = _lease_id(run_id, message_id)
    redis_client = redis.from_url(settings.REDIS_URL)

    # 延迟到达或重复投递的 Worker 不能重启已经结束的任务。
    if getattr(task, "status", None) not in {"queued", "running"}:
        db.rollback()
        return task
    if celery_task_id and getattr(task, "celery_task_id", None) != celery_task_id:
        db.rollback()
        return task

    # 新任务只允许 queued -> running。started_at/heartbeat_at 都存在时说明另一个
    # Worker 已经开始执行，当前消息是重复投递，直接返回避免重复压测。
    if (
        task.status == "running"
        and getattr(task, "started_at", None) is not None
        and getattr(task, "heartbeat_at", None) is not None
    ):
        db.rollback()
        return task

    if not _acquire_run_lock(redis_client, lease_id, task.duration):
        perf_repo.db_update_if_status_in(
            db,
            task_id,
            project_id,
            ("queued", "running"),
            status="failed",
            finished_at=_utcnow(),
            failure_reason="Locust master 已被其他压测任务占用",
        )
        raise PerfRunBusyError("Locust master 已被其他压测任务占用")

    cancel_key = f"locust:cancel:{project_id}:{task_id}"
    base = settings.LOCUST_MASTER_URL
    stats = {}
    history_samples = []
    started = False
    stopped = False
    claimed = False
    def heartbeat():
        if perf_repo.db_touch_heartbeat(db, task_id, project_id, _utcnow()) is None:
            raise RuntimeError("压测任务已不再处于运行状态")
        _refresh_run_keys(redis_client, run_id, task.duration)

    try:
        now = _utcnow()
        if task.status == "queued":
            task = perf_repo.db_update_if_status(
                db,
                task_id,
                project_id,
                "queued",
                status="running",
                celery_task_id=celery_task_id or getattr(task, "celery_task_id", None),
                started_at=now,
                heartbeat_at=now,
                failure_reason=None,
            )
            if task is None:
                return perf_repo.db_get(db, task_id, project_id)
        else:
            # 兼容升级前已经处于 running、但没有生命周期时间戳的任务。
            task = perf_repo.db_update_if_status(
                db,
                task_id,
                project_id,
                "running",
                celery_task_id=celery_task_id or getattr(task, "celery_task_id", None),
                started_at=now,
                heartbeat_at=now,
                failure_reason=None,
            )
            if task is None:
                return perf_repo.db_get(db, task_id, project_id)
        claimed = True
        with _locust_control(redis_client):
            if _decode_redis_value(redis_client.get(RUN_LOCK_KEY)) != lease_id:
                raise RuntimeError("压测执行锁已丢失，禁止启动任务")
            if redis_client.get(cancel_key) or perf_repo.db_touch_heartbeat(
                db, task_id, project_id, _utcnow(),
            ) is None:
                return perf_repo.db_get(db, task_id, project_id)
            ttl = _run_ttl(task.duration)
            load_config = getattr(task, "load_config", None)
            target = json.dumps({"lease": lease_id, "target_host": task.target_host,
                                 "deadline": time.time() + task.duration,
                                 "load_config": load_config}, ensure_ascii=False) if load_config else task.target_path
            redis_client.set(_target_path_key(run_id), target, ex=ttl)
            redis_client.set(ACTIVE_RUN_KEY, run_id, ex=ttl)
            # Even a timeout may mean the master accepted the request. Keep both
            # locks until it returns so cancellation/recovery cannot admit a
            # newer run that this old HTTP request would subsequently overwrite.
            started = True
            response = requests.post(f"{base}/swarm", data={
                "user_count": task.users,
                "spawn_rate": task.spawn_rate,
                "host": task.target_host,
                "run_time": f"{max(1, task.duration)}s",
            }, headers=_control_headers(), timeout=_control_timeout())
            response.raise_for_status()
            if response.json().get("success") is False:
                raise PerfControlUnavailableError("Locust 未接受启动请求")

        elapsed = 0
        while elapsed < task.duration:
            if _decode_redis_value(redis_client.get(RUN_LOCK_KEY)) != lease_id:
                raise RuntimeError("压测执行锁已丢失")
            if redis_client.get(cancel_key):
                _stop_owned_run(redis_client, lease_id)
                stopped = True
                return perf_repo.db_update_if_status(db, task_id, project_id, "running", status="cancelled") or perf_repo.db_get(db, task_id, project_id)
            pause = max(0.01, min(2, settings.PERF_HEARTBEAT_TIMEOUT_SECONDS / 4))
            time.sleep(pause)
            elapsed += pause
            heartbeat()
            stats = _control_get_json(base, "/stats/requests")
            heartbeat()  # Do not stack two blocking control calls under one heartbeat.
            iteration_stats = _control_get_json(base, "/whale/iterations")
            heartbeat()
            _validate_iterations(iteration_stats, lease_id)
            aggregate = next((row for row in stats.get("stats", []) if row.get("name") == "Aggregated"), {})
            transactions = transaction_sample(iteration_stats, history_samples[-1] if history_samples else None)
            history_samples.append({"elapsed_s": elapsed, "sampled_at": _utcnow().isoformat() + "Z", "rps": stats.get("total_rps") or 0, "fail_ratio": stats.get("fail_ratio") or 0, "users": stats.get("user_count") or 0, "avg_response_ms": aggregate.get("avg_response_time"), "p95_response_ms": aggregate.get("response_time_percentile_0.95", aggregate.get("95th_percentile")), "p99_response_ms": aggregate.get("response_time_percentile_0.99", aggregate.get("99th_percentile"))})
            history_samples[-1].update(transactions)
            # Bound repeated JSON writes on long runs; request counters remain cumulative.
            del history_samples[:-MAX_LIVE_HISTORY_SAMPLES]
            live = _result_statistics(stats, None, {}, history_samples, allow_empty=True)
            live["iteration_stats"] = iteration_stats
            # One conditional commit makes the complete sample visible to API readers.
            # A concurrent stop must never be overwritten or revived by a late sample.
            if perf_repo.db_update_if_status(db, task_id, project_id, "running", **live) is None:
                _stop_owned_run(redis_client, lease_id)
                stopped = True
                return perf_repo.db_get(db, task_id, project_id)
            metrics.perf_rps.set(stats.get("total_rps") or 0)
            metrics.perf_fail_ratio.set(stats.get("fail_ratio") or 0)
            metrics.perf_user_count.set(stats.get("user_count") or 0)
            for row in stats.get("stats", []):
                if row.get("name") == "Aggregated":
                    metrics.perf_avg_response_ms.set(row.get("avg_response_time") or 0)

        # Final counters include late worker reports, but stopped instantaneous
        # RPS is not a replacement for the last live sample shown in history.
        live_rps = stats.get("total_rps")
        live_endpoint_rps = {(row.get("method"), row.get("name")): row.get("current_rps", row.get("rps"))
                             for row in stats.get("stats", [])}
        heartbeat()
        _stop_owned_run(redis_client, lease_id)
        stopped = True
        heartbeat()
        # Legacy tasks must also prove the master started THIS lease; old stats
        # from a previous run are not evidence that a no-worker swarm started.
        time.sleep(min(0.25, _control_timeout()))
        iteration_stats = _control_get_json(base, "/whale/iterations")
        heartbeat()
        _validate_iterations(iteration_stats, lease_id)
        perf_repo.db_update_if_status(db, task_id, project_id, "running", iteration_stats=iteration_stats)
        stats = _control_get_json(base, "/stats/requests")
        heartbeat()
        result_stats = _result_statistics(stats, live_rps, live_endpoint_rps, history_samples)
        finished_at = _utcnow()
        return perf_repo.db_update_if_status(db, task_id, project_id, "running", status="done", heartbeat_at=finished_at, finished_at=finished_at, failure_reason=None, **result_stats)
    except Exception as exc:
        current = perf_repo.db_get(db, task_id, project_id)
        if current is not None and getattr(current, "status", None) == "cancelled":
            return current
        try:
            perf_repo.db_update_if_status_in(
                db,
                task_id,
                project_id,
                ("queued", "running"),
                status="failed",
                finished_at=_utcnow(),
                failure_reason=str(exc)[:500],
            )
        except Exception:
            db.rollback()
        raise
    finally:
        if claimed:
            metrics.perf_rps.set(0)
            metrics.perf_fail_ratio.set(0)
            metrics.perf_user_count.set(0)
            metrics.perf_avg_response_ms.set(0)
            try:
                _cleanup_run(redis_client, run_id, lease_id, started and not stopped)
            except Exception:
                pass


def s_mark_queued(
    db: Session,
    task_id: int,
    project_id: int,
    celery_task_id: str,
):
    # Same lock order as project cascade deletion, held until queue CAS commits.
    if project_repo.db_lock_project(db, project_id) is None:
        db.rollback()
        return None
    task = perf_repo.db_get_for_update(db, task_id, project_id)
    if task is None:
        db.rollback()
        return None
    if task.status in {"queued", "running"}:
        db.rollback()
        raise PerfRunBusyError("压测任务已不再处于待执行状态，请刷新后重试")
    try:
        _control_headers()  # Fail before reserving a lease or publishing any message.
    except Exception:
        db.rollback()
        raise
    redis_client = redis.from_url(settings.REDIS_URL)
    run_id = _run_id(project_id, task_id)
    lease_id = _lease_id(run_id, celery_task_id)
    # Admission is never reentrant, even if a caller retries the same Celery ID.
    # Only the Worker may adopt an already reserved execution lease.
    try:
        if not redis_client.set(RUN_LOCK_KEY, lease_id, nx=True, ex=_run_ttl(task.duration)):
            db.rollback()
            raise PerfRunBusyError("已有压测任务正在排队或运行")
        perf_repo._sync_run(db, task_id, project_id)
        redis_client.delete(f"locust:cancel:{project_id}:{task_id}")
        reset = {field: None for field in RESULT_FIELDS if field not in {
            "status", "celery_task_id", "queued_at"}}
        updated = perf_repo.db_update_if_status(
            db,
            task_id,
            project_id,
            task.status,
            status="queued",
            celery_task_id=celery_task_id,
            queued_at=_utcnow(),
            **reset,
        )
        if updated is None:
            _release_run_lock(redis_client, run_id, lease_id)
        return updated
    except PerfRunBusyError:
        raise  # Never release another HTTP request's lease (even the same ID).
    except Exception:
        db.rollback()
        _release_run_lock(redis_client, run_id, lease_id)
        raise


def s_cancel(db: Session, task_id: int, project_id: int, execution_id: str | None = None):
    if project_repo.db_lock_project(db, project_id) is None:
        db.rollback()
        return None
    task = perf_repo.db_get_for_update(db, task_id, project_id)
    if task is None:
        db.rollback()
        return None
    if execution_id and task.celery_task_id != execution_id:
        db.rollback()
        raise PerfRunBusyError("执行记录已变化，请刷新后重试")
    if task.status not in {"queued", "running"}:
        return task
    redis_client = redis.from_url(settings.REDIS_URL)
    # Only a successful queued -> cancelled CAS proves no Worker has claimed
    # the task. A stale queued snapshot must never free a running Worker's lease.
    result = perf_repo.db_update_if_status(
        db,
        task_id,
        project_id,
        "queued",
        status="cancelled",
        finished_at=_utcnow(),
        failure_reason=None,
    )
    run_id = _run_id(project_id, task_id)
    if result is not None:
        _release_run_lock(redis_client, run_id, _lease_id(run_id, getattr(task, "celery_task_id", None) or "legacy"))
        return result
    redis_client.set(f"locust:cancel:{project_id}:{task_id}", "1", ex=86400)
    result = perf_repo.db_update_if_status(
        db, task_id, project_id, "running", status="cancelled",
        finished_at=_utcnow(), failure_reason=None,
    )
    # A running launch may not have published ACTIVE yet. Its Worker (or the
    # serialized reconciler) stops/cleans up before releasing the execution lease.
    return result or perf_repo.db_get(db, task_id, project_id)




def s_mark_failed(db: Session, task_id: int, project_id: int):
    result = perf_repo.db_update_if_status_in(
        db,
        task_id,
        project_id,
        ("queued", "running"),
        status="failed",
        finished_at=_utcnow(),
        failure_reason="压测任务未成功投递到 RabbitMQ",
    )
    try:
        redis_client = redis.from_url(settings.REDIS_URL)
        if result is not None:
            run_id = _run_id(project_id, task_id)
            _cleanup_run(redis_client, run_id, _lease_id(run_id, result.celery_task_id), True)
    except Exception:
        pass
    return result


def s_reconcile_stale(
    db: Session,
    project_id: int | None = None,
) -> dict[str, int]:
    """Fail tasks abandoned by an unavailable or abruptly terminated Worker."""
    now = _utcnow()
    failed = perf_repo.db_fail_stale(
        db,
        queued_before=now - timedelta(seconds=settings.PERF_QUEUE_TIMEOUT_SECONDS),
        running_before=now - timedelta(seconds=settings.PERF_HEARTBEAT_TIMEOUT_SECONDS),
        finished_at=now,
        project_id=project_id,
    )
    for task_id, project_id, previous_status in failed:
        metrics.perf_stale_tasks_recovered.labels(
            previous_status=previous_status,
        ).inc()
    # Also retry cleanup for tasks already failed/cancelled during an earlier
    # control-plane outage. Inspect only the current lease, not all old reports.
    try:
        redis_client = redis.from_url(settings.REDIS_URL)
        lease = _decode_redis_value(redis_client.get(RUN_LOCK_KEY))
        if lease:
            parts = lease.split(":", 2)
            if len(parts) == 3:
                owner_project, owner_task = int(parts[0]), int(parts[1])
                task = perf_repo.db_get(db, owner_task, owner_project)
                if task is None or task.status in {"done", "failed", "cancelled"}:
                    active = _decode_redis_value(redis_client.get(ACTIVE_RUN_KEY))
                    run_id = _run_id(owner_project, owner_task)
                    _cleanup_run(redis_client, run_id, lease, task is None or active == run_id)
    except Exception:
        pass
    return {"failed": len(failed)}


def s_clear_runs(db, task_id, project_id, selection):
    if project_repo.db_lock_project(db, project_id) is None:
        db.rollback()
        return None
    task = perf_repo.db_get_for_update(db, task_id, project_id)
    if task is None:
        db.rollback()
        return None
    try:
        if task.status in {"done", "failed", "cancelled"}:
            # A cancelled worker may still own the singleton lease. Finish its
            # cleanup before resetting the definition to pending, so recovery
            # cannot lose the owner and leave all later runs blocked.
            redis_client = redis.from_url(settings.REDIS_URL)
            try:
                lease = _decode_redis_value(redis_client.get(RUN_LOCK_KEY))
            except redis.RedisError as exc:
                raise PerfControlUnavailableError("无法检查压测执行锁，请稍后重试清理") from exc
            run_id = _run_id(project_id, task_id)
            if lease and lease.startswith(f"{run_id}:"):
                if not _cleanup_run(redis_client, run_id, lease, needs_stop=True):
                    raise PerfControlUnavailableError("上一轮执行仍在清理，请稍后重试")
        return perf_repo.db_clear_runs(db, task, selection)
    except Exception:
        db.rollback()
        raise
