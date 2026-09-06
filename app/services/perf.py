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

    perf_repo.db_update(db, task_id, project_id, status="running")
    redis_client = redis.from_url(settings.REDIS_URL)
    cancel_key = f"locust:cancel:{project_id}:{task_id}"
    delete_cancel = getattr(redis_client, "delete", None)
    if delete_cancel:
        delete_cancel(cancel_key)
    base = settings.LOCUST_MASTER_URL
    stats = {}
    started = False
    stopped = False
    try:
        redis_client.set("locust:target_path", task.target_path)
        response = requests.post(f"{base}/swarm", data={
            "user_count": task.users,
            "spawn_rate": task.spawn_rate,
            "host": task.target_host,
        })
        response.raise_for_status()
        started = True

        elapsed = 0
        while elapsed < task.duration:
            if redis_client.get(cancel_key):
                requests.get(f"{base}/stop", timeout=5)
                stopped = True
                return perf_repo.db_update(db, task_id, project_id, status="cancelled")
            time.sleep(2)
            elapsed += 2
            stats = requests.get(f"{base}/stats/requests").json()
            metrics.perf_rps.set(stats.get("total_rps") or 0)
            metrics.perf_fail_ratio.set(stats.get("fail_ratio") or 0)
            metrics.perf_user_count.set(stats.get("user_count") or 0)
            for row in stats.get("stats", []):
                if row.get("name") == "Aggregated":
                    metrics.perf_avg_response_ms.set(row.get("avg_response_time") or 0)

        requests.get(f"{base}/stop").raise_for_status()
        stopped = True
        rps = stats.get("total_rps")
        fail_ratio = stats.get("fail_ratio")
        avg = next((row.get("avg_response_time") for row in stats.get("stats", []) if row.get("name") == "Aggregated"), None)
        return perf_repo.db_update(db, task_id, project_id, status="done", rps=rps, avg_response_ms=avg, fail_ratio=fail_ratio)
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
                requests.get(f"{base}/stop")
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
    try:
        requests.get(f"{settings.LOCUST_MASTER_URL}/stop", timeout=5)
    except Exception:
        pass
    return perf_repo.db_update(db, task_id, project_id, status="cancelled")


