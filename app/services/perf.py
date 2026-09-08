import time
import redis
import requests
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core import metrics
from app.repositories import perf as perf_repo


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

    # 取消状态是终态，延迟启动的 worker 不能把它重新改回 running。
    if getattr(task, "status", None) == "cancelled":
        return task

    # /run 路由通常已经置为 running；直接调用 worker 时才补齐状态。
    if getattr(task, "status", None) != "running":
        task = perf_repo.db_update(db, task_id, project_id, status="running") or task
    redis_client = redis.from_url(settings.REDIS_URL)
    cancel_key = f"locust:cancel:{project_id}:{task_id}"
    delete_cancel = getattr(redis_client, "delete", None)
    if delete_cancel:
        delete_cancel(cancel_key)
    base = settings.LOCUST_MASTER_URL
    stats = {}
    history_samples = []
    started = False
    stopped = False
    try:
        redis_client.set("locust:target_path", task.target_path)
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


def s_mark_running(db: Session, task_id: int, project_id: int):
    task = perf_repo.db_get(db, task_id, project_id)
    if task is None or task.status != "pending":
        return None
    return perf_repo.db_update(db, task_id, project_id, status="running")


def s_cancel(db: Session, task_id: int, project_id: int):
    task = perf_repo.db_get(db, task_id, project_id)
    if task is None:
        return None
    if task.status != "running":
        return task
    redis_client = redis.from_url(settings.REDIS_URL)
    redis_client.set(f"locust:cancel:{project_id}:{task_id}", "1", ex=86400)
    return perf_repo.db_update_if_status(db, task_id, project_id, "running", status="cancelled")




def s_mark_failed(db: Session, task_id: int, project_id: int):
    return perf_repo.db_update_if_status(db, task_id, project_id, 'running', status='failed')
