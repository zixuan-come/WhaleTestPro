import time
import redis
import requests
from app.core.config import settings
from app.core import metrics
from app.repositories import perf as perf_repo

def s_create(db, perf):
    return perf_repo.db_create(db, perf)


def s_get(db, task_id):
    return perf_repo.db_get(db, task_id)


def s_list(db):
    return perf_repo.db_list(db)


def s_delete(db, task_id):
    return perf_repo.db_delete(db, task_id)


def s_run(db, task_id):
    task = perf_repo.db_get(db, task_id)
    if task is None:
        return None

    perf_repo.db_update(db, task_id, status="running")

    base = settings.LOCUST_MASTER_URL

    # 把这次要打的 path 写进本地 Redis，master 在 test_start 读出来广播给 worker
    redis.from_url(settings.REDIS_URL).set("locust:target_path", task.target_path)

    requests.post(f"{base}/swarm", data={
        "user_count": task.users,
        "spawn_rate": task.spawn_rate,
        "host": task.target_host,
    })

    # 每 2 秒采一次，刷新内存指标 → Prometheus 抓到的是实时曲线而非单点
    elapsed = 0
    stats = {}
    while elapsed < task.duration:
        time.sleep(2)
        elapsed += 2
        stats = requests.get(f"{base}/stats/requests").json()
        metrics.perf_rps.set(stats.get("total_rps") or 0)
        metrics.perf_fail_ratio.set(stats.get("fail_ratio") or 0)
        metrics.perf_user_count.set(stats.get("user_count") or 0)
        for row in stats.get("stats", []):
            if row.get("name") == "Aggregated":
                metrics.perf_avg_response_ms.set(row.get("avg_response_time") or 0)

    # stop 会重置统计；上面循环最后一次采样已留在 stats 里，下面写库复用它
    requests.get(f"{base}/stop")

    # 压测结束清零，否则曲线会卡在最后一个值一直横着，看着像还在压
    metrics.perf_rps.set(0)
    metrics.perf_fail_ratio.set(0)
    metrics.perf_user_count.set(0)
    metrics.perf_avg_response_ms.set(0)

    rps = stats.get("total_rps")
    fail_ratio = stats.get("fail_ratio")
    avg = None
    for row in stats.get("stats", []):
        if row.get("name") == "Aggregated":
            avg = row.get("avg_response_time")
            break

    return perf_repo.db_update(
        db, task_id,
        status="done",
        rps=rps,
        avg_response_ms=avg,
        fail_ratio=fail_ratio,
    )


def s_mark_running(db, task_id):
    task = perf_repo.db_get(db, task_id)
    if task is None:
        return None
    return perf_repo.db_update(db, task_id, status="running")







