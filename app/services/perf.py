import time
import redis
import requests
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core import metrics
from app.repositories import perf as perf_repo


RUN_LOCK_KEY = "locust:run_lock"
ACTIVE_RUN_KEY = "locust:active_run"
RUN_LOCK_GRACE_SECONDS = 300


class PerfRunBusyError(RuntimeError):
    """Raised when the singleton Locust master is already serving another run."""


def _run_id(project_id: int, task_id: int) -> str:
    return f"{project_id}:{task_id}"


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


def _release_run_lock(redis_client, run_id: str) -> int:
    script = """
    if redis.call('get', KEYS[1]) ~= ARGV[1] then
        return 0
    end
    if redis.call('get', KEYS[2]) == ARGV[1] then
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
        run_id,
    )


def s_create(db: Session, perf, project_id: int):
    return perf_repo.db_create(db, perf, project_id)


def s_get(db: Session, task_id: int, project_id: int):
    return perf_repo.db_get(db, task_id, project_id)


def s_list(db: Session, project_id: int):
    return perf_repo.db_list(db, project_id)


def s_delete(db: Session, task_id: int, project_id: int):
    task = perf_repo.db_get(db, task_id, project_id)
    if task is None or task.status == "running":
        return None
    return perf_repo.db_delete(db, task_id, project_id)


def s_run(db: Session, task_id: int, project_id: int):
    task = perf_repo.db_get(db, task_id, project_id)
    if task is None:
        return None
    run_id = _run_id(project_id, task_id)
    redis_client = redis.from_url(settings.REDIS_URL)

    # 取消状态是终态，延迟启动的 worker 不能把它重新改回 running。
    if getattr(task, "status", None) == "cancelled":
        try:
            _release_run_lock(redis_client, run_id)
        except Exception:
            pass
        return task

    if not _acquire_run_lock(redis_client, run_id, task.duration):
        perf_repo.db_update_if_status(
            db,
            task_id,
            project_id,
            "running",
            status="failed",
        )
        raise PerfRunBusyError("Locust master 已被其他压测任务占用")

    cancel_key = f"locust:cancel:{project_id}:{task_id}"
    base = settings.LOCUST_MASTER_URL
    stats = {}
    history_samples = []
    started = False
    stopped = False
    try:
        # /run 路由通常已经置为 running；直接调用 worker 时才补齐状态。
        if getattr(task, "status", None) != "running":
            task = perf_repo.db_update(db, task_id, project_id, status="running") or task
        redis_client.delete(cancel_key)
        ttl = _run_ttl(task.duration)
        redis_client.set(_target_path_key(run_id), task.target_path, ex=ttl)
        redis_client.set(ACTIVE_RUN_KEY, run_id, ex=ttl)
        response = requests.post(f"{base}/swarm", data={
            "user_count": task.users,
            "spawn_rate": task.spawn_rate,
            "host": task.target_host,
        }, timeout=settings.REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        started = True

        elapsed = 0
        while elapsed < task.duration:
            if redis_client.get(cancel_key):
                requests.get(f"{base}/stop", timeout=settings.REQUEST_TIMEOUT_SECONDS)
                stopped = True
                return perf_repo.db_update_if_status(db, task_id, project_id, "running", status="cancelled")
            time.sleep(2)
            elapsed += 2
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

        requests.get(f"{base}/stop", timeout=settings.REQUEST_TIMEOUT_SECONDS).raise_for_status()
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
        return perf_repo.db_update_if_status(db, task_id, project_id, "running", status="done", rps=rps, avg_response_ms=avg, p95_response_ms=p95, p99_response_ms=p99, fail_ratio=fail_ratio, request_stats=request_stats or None, error_summary=error_summary or None, history_samples=history_samples or None)
    except Exception:
        current = perf_repo.db_get(db, task_id, project_id)
        if current is not None and getattr(current, "status", None) == "cancelled":
            return current
        try:
            perf_repo.db_update(db, task_id, project_id, status="failed")
        except Exception:
            db.rollback()
        raise
    finally:
        if started and not stopped:
            try:
                requests.get(f"{base}/stop", timeout=settings.REQUEST_TIMEOUT_SECONDS)
            except Exception:
                pass
        metrics.perf_rps.set(0)
        metrics.perf_fail_ratio.set(0)
        metrics.perf_user_count.set(0)
        metrics.perf_avg_response_ms.set(0)
        try:
            _release_run_lock(redis_client, run_id)
        except Exception:
            pass


def s_mark_running(db: Session, task_id: int, project_id: int):
    task = perf_repo.db_get(db, task_id, project_id)
    if task is None or task.status != "pending":
        return None
    redis_client = redis.from_url(settings.REDIS_URL)
    run_id = _run_id(project_id, task_id)
    if not _acquire_run_lock(redis_client, run_id, task.duration):
        raise PerfRunBusyError("已有压测任务正在运行")
    try:
        updated = perf_repo.db_update(db, task_id, project_id, status="running")
        if updated is None:
            _release_run_lock(redis_client, run_id)
        return updated
    except Exception:
        _release_run_lock(redis_client, run_id)
        raise


def s_cancel(db: Session, task_id: int, project_id: int):
    task = perf_repo.db_get(db, task_id, project_id)
    if task is None:
        return None
    if task.status != "running":
        return task
    redis_client = redis.from_url(settings.REDIS_URL)
    redis_client.set(f"locust:cancel:{project_id}:{task_id}", "1", ex=86400)
    result = perf_repo.db_update_if_status(db, task_id, project_id, "running", status="cancelled")
    run_id = _run_id(project_id, task_id)
    active_run = _decode_redis_value(redis_client.get(ACTIVE_RUN_KEY))
    if active_run != run_id:
        _release_run_lock(redis_client, run_id)
    return result




def s_mark_failed(db: Session, task_id: int, project_id: int):
    result = perf_repo.db_update_if_status(db, task_id, project_id, 'running', status='failed')
    try:
        redis_client = redis.from_url(settings.REDIS_URL)
        _release_run_lock(redis_client, _run_id(project_id, task_id))
    except Exception:
        pass
    return result
