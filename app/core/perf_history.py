"""Versioned run snapshots and transaction throughput, independent of external IO."""
from datetime import datetime

RESULT_FIELDS = (
    "status", "celery_task_id", "queued_at", "started_at", "heartbeat_at", "finished_at",
    "failure_reason", "rps", "avg_response_ms", "p95_response_ms", "p99_response_ms",
    "request_stats", "error_summary", "history_samples", "iteration_stats", "fail_ratio",
)
DATE_FIELDS = {"queued_at", "started_at", "heartbeat_at", "finished_at"}


def run_snapshot(values):
    return {key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in values.items()}


def execution_key(values):
    return values.get("celery_task_id") or f"legacy:{values['id']}"


def transaction_sample(summary, previous=None):
    """One declared iteration is one transaction; rates include failed completions."""
    count = summary.get("iterations")
    failures = summary.get("failures")
    elapsed = summary.get("elapsed_seconds")
    if (type(count) is not int or type(failures) is not int or count < 0
            or failures < 0 or failures > count or not isinstance(elapsed, (int, float)) or elapsed <= 0):
        return {}
    previous = previous or {}
    before_count = previous.get("transactions", 0)
    before_failures = previous.get("failed_transactions", 0)
    delta_time = elapsed - previous.get("transaction_elapsed_s", 0)
    delta_count = count - before_count
    delta_failures = failures - before_failures
    valid_delta = delta_time > 0 and 0 <= delta_failures <= delta_count
    return {
        "transactions": count, "failed_transactions": failures, "transaction_elapsed_s": elapsed,
        "avg_tps": count / elapsed, "success_tps": (count - failures) / elapsed,
        "transaction_fail_ratio": failures / count if count else 0,
        "tps": delta_count / delta_time if valid_delta else None,
        "current_success_tps": (delta_count - delta_failures) / delta_time if valid_delta else None,
    }
