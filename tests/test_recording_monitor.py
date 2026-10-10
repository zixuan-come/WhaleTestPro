from app.core.recording_monitor import RecordingFailureMonitor
import io
import logging

import pytest

from app.schemas.traffic_record import TrafficRecordCreate


class _Counter:
    def __init__(self):
        self.value = 0

    def inc(self):
        self.value += 1


class _Logger:
    def __init__(self):
        self.calls = []

    def warning(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def test_recording_failures_are_all_counted_but_logs_are_rate_limited():
    counter = _Counter()
    log = _Logger()
    times = iter([0.0, 10.0, 61.0])
    monitor = RecordingFailureMonitor(
        counter=counter,
        log_interval_seconds=60,
        clock=lambda: next(times),
        log=log,
    )

    for _ in range(3):
        monitor.report(
            RuntimeError("secret broker details"),
            method="POST",
            path="/orders/1",
        )

    assert counter.value == 3
    assert len(log.calls) == 2
    assert all("secret broker details" not in str(call) for call in log.calls)
    assert all(not call[1].get("exc_info") for call in log.calls)


@pytest.mark.parametrize("error_kind", ["broker", "validation"])
def test_formatted_recording_log_excludes_sensitive_exception_input(error_kind):
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    log = logging.Logger("isolated-recording-confidentiality", level=logging.WARNING)
    log.addHandler(handler)
    counter = _Counter()
    monitor = RecordingFailureMonitor(counter=counter, log=log)
    secret = "synthetic-sensitive-request-or-broker-secret"
    try:
        try:
            if error_kind == "validation":
                TrafficRecordCreate(method="POST", path="/cases", response_status=200,
                                    project_id=1, request_body=secret)
            raise RuntimeError(secret)
        except Exception as exc:
            monitor.report(exc, method="POST", path="/cases")
        rendered = output.getvalue()
        assert counter.value == 1
        assert "traffic recording enqueue failed" in rendered
        assert "error_type=" in rendered
        assert secret not in rendered
        assert "Traceback" not in rendered
    finally:
        log.removeHandler(handler)
        handler.close()
