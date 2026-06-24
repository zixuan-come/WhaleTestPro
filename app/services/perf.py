import os
import sys
import csv
import subprocess
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

    cmd = [
        sys.executable, "-m", "locust",
        "-f", "locustfile.py",
        "--headless",
        "-u", str(task.users),
        "-r", str(task.spawn_rate),
        "-t", f"{task.duration}s",
        "--host", task.target_host,
        "--csv", "perf_result",
        "--only-summary",
    ]
    env = {**os.environ, "TARGET_PATH": task.target_path}
    subprocess.run(cmd, env=env, capture_output=True, text=True)
    rps = avg = fail_ratio = None
    with open("perf_result_stats.csv", newline="") as f:
        for row in csv.DictReader(f):
            if row["Name"] == "Aggregated":
                req_count = int(row["Request Count"])
                fail_count = int(row["Failure Count"])
                rps = float(row["Requests/s"])
                avg = float(row["Average Response Time"])
                fail_ratio = fail_count / req_count if req_count else 0.0
                break

    return perf_repo.db_update(
        db, task_id,
        status="done",
        rps=rps,
        avg_response_ms=avg,
        fail_ratio=fail_ratio,
    )













