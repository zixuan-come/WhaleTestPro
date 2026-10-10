import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import redis
import requests
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core import metrics
from app.repositories import perf as perf_repo


RUN_LOCK_KEY = "locust:run_lock"
ACTIVE_RUN_KEY = "locust:active_run"
CONTROL_LOCK_KEY = "locust:control_lock"
RUN_LOCK_GRACE_SECONDS = 300


class PerfRunBusyError(RuntimeError):
    """Raised when the singleton Locust master is already serving another run."""


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
        timeout=settings.REQUEST_TIMEOUT_SECONDS,
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
    return perf_repo.db_get(db, task_id, project_id)


def s_list(db: Session, project_id: int):
    s_reconcile_stale(db, project_id=project_id)
    return perf_repo.db_list(db, project_id)


def s_delete(db: Session, task_id: int, project_id: int):
    task = perf_repo.db_get(db, task_id, project_id)
    if task is None or task.status in {"queued", "running"}:
        return None
    return perf_repo.db_delete(db, task_id, project_id)


def s_run(
    db: Session,
    task_id: int,
    project_id: int,
    celery_task_id: str | None = None,
):
    task = perf_repo.db_get(db, task_id, project_id)
    if task is None:
        return None
    run_id = _run_id(project_id, task_id)
    message_id = celery_task_id or getattr(task, "celery_task_id", None) or "legacy"
    lease_id = _lease_id(run_id, message_id)
    redis_client = redis.from_url(settings.REDIS_URL)

    # 延迟到达或重复投递的 Worker 不能重启已经结束的任务。
    if getattr(task, "status", None) not in {"queued", "running"}:
        return task
    if celery_task_id and getattr(task, "celery_task_id", None) != celery_task_id:
        return task

    # 新任务只允许 queued -> running。started_at/heartbeat_at 都存在时说明另一个
    # Worker 已经开始执行，当前消息是重复投递，直接返回避免重复压测。
    if (
        task.status == "running"
        and getattr(task, "started_at", None) is not None
        and getattr(task, "heartbeat_at", None) is not None
    ):
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
            redis_client.set(_target_path_key(run_id), task.target_path, ex=ttl)
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
            }, timeout=settings.REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()

        elapsed = 0
        while elapsed < task.duration:
            if _decode_redis_value(redis_client.get(RUN_LOCK_KEY)) != lease_id:
                raise RuntimeError("压测执行锁已丢失")
            if redis_client.get(cancel_key):
                _stop_owned_run(redis_client, lease_id)
                stopped = True
                return perf_repo.db_update_if_status(db, task_id, project_id, "running", status="cancelled") or perf_repo.db_get(db, task_id, project_id)
            time.sleep(2)
            elapsed += 2
            heartbeat_at = _utcnow()
            if perf_repo.db_touch_heartbeat(
                db,
                task_id,
                project_id,
                heartbeat_at,
            ) is None:
                raise RuntimeError("压测任务已不再处于运行状态")
            _refresh_run_keys(redis_client, run_id, task.duration)
            stats = requests.get(f"{base}/stats/requests", timeout=settings.REQUEST_TIMEOUT_SECONDS).json()
            aggregate = next((row for row in stats.get("stats", []) if row.get("name") == "Aggregated"), {})
            history_samples.append({"elapsed_s": elapsed, "rps": stats.get("total_rps") or 0, "fail_ratio": stats.get("fail_ratio") or 0, "users": stats.get("user_count") or 0, "avg_response_ms": aggregate.get("avg_response_time"), "p95_response_ms": aggregate.get("response_time_percentile_0.95", aggregate.get("95th_percentile")), "p99_response_ms": aggregate.get("response_time_percentile_0.99", aggregate.get("99th_percentile"))})
            metrics.perf_rps.set(stats.get("total_rps") or 0)
            metrics.perf_fail_ratio.set(stats.get("fail_ratio") or 0)
            metrics.perf_user_count.set(stats.get("user_count") or 0)
            for row in stats.get("stats", []):
                if row.get("name") == "Aggregated":
                    metrics.perf_avg_response_ms.set(row.get("avg_response_time") or 0)

        _stop_owned_run(redis_client, lease_id)
        stopped = True
        rps = stats.get("total_rps")
        fail_ratio = stats.get("fail_ratio")
        aggregate = next((row for row in stats.get("stats", []) if row.get("name") == "Aggregated"), {})
        avg = aggregate.get("avg_response_time")
        p95 = aggregate.get("response_time_percentile_0.95", aggregate.get("95th_percentile"))
        p99 = aggregate.get("response_time_percentile_0.99", aggregate.get("99th_percentile"))
        request_stats = [
            {"name": row.get("name"), "method": row.get("method"), "num_requests": row.get("num_requests", 0), "num_failures": row.get("num_failures", 0), "rps": row.get("current_rps", row.get("rps")), "avg_response_ms": row.get("avg_response_time"), "p95_response_ms": row.get("response_time_percentile_0.95", row.get("95th_percentile")), "p99_response_ms": row.get("response_time_percentile_0.99", row.get("99th_percentile"))}
            for row in stats.get("stats", []) if row.get("name") != "Aggregated"
        ]
        error_summary = [{"name": row.get("name"), "method": row.get("method"), "error_count": row.get("num_failures", 0), "error_rate": (row.get("num_failures", 0) / row.get("num_requests", 1)) if row.get("num_requests", 0) else 0, "message": row.get("error") or row.get("last_error")} for row in stats.get("errors", [])]
        finished_at = _utcnow()
        return perf_repo.db_update_if_status(db, task_id, project_id, "running", status="done", heartbeat_at=finished_at, finished_at=finished_at, failure_reason=None, rps=rps, avg_response_ms=avg, p95_response_ms=p95, p99_response_ms=p99, fail_ratio=fail_ratio, request_stats=request_stats or None, error_summary=error_summary or None, history_samples=history_samples or None)
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
    task = perf_repo.db_get(db, task_id, project_id)
    if task is None or task.status != "pending":
        return None
    redis_client = redis.from_url(settings.REDIS_URL)
    run_id = _run_id(project_id, task_id)
    lease_id = _lease_id(run_id, celery_task_id)
    # Admission is never reentrant, even if a caller retries the same Celery ID.
    # Only the Worker may adopt an already reserved execution lease.
    if not redis_client.set(RUN_LOCK_KEY, lease_id, nx=True, ex=_run_ttl(task.duration)):
        raise PerfRunBusyError("已有压测任务正在排队或运行")
    try:
        updated = perf_repo.db_update_if_status(
            db,
            task_id,
            project_id,
            "pending",
            status="queued",
            celery_task_id=celery_task_id,
            queued_at=_utcnow(),
            started_at=None,
            heartbeat_at=None,
            finished_at=None,
            failure_reason=None,
        )
        if updated is None:
            _release_run_lock(redis_client, run_id, lease_id)
        return updated
    except Exception:
        _release_run_lock(redis_client, run_id, lease_id)
        raise


def s_cancel(db: Session, task_id: int, project_id: int):
    task = perf_repo.db_get(db, task_id, project_id)
    if task is None:
        return None
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
                if task is not None and task.status in {"failed", "cancelled"}:
                    active = _decode_redis_value(redis_client.get(ACTIVE_RUN_KEY))
                    run_id = _run_id(owner_project, owner_task)
                    _cleanup_run(redis_client, run_id, lease, active == run_id)
    except Exception:
        pass
    return {"failed": len(failed)}
