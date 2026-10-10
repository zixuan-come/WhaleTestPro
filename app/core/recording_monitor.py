import logging
import threading
import time
from collections.abc import Callable

from app.core.metrics import traffic_record_enqueue_failures


logger = logging.getLogger(__name__)


class RecordingFailureMonitor:
    """Count every recording failure and rate-limit equivalent log noise."""

    def __init__(
        self,
        *,
        counter=traffic_record_enqueue_failures,
        log_interval_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        log=logger,
    ) -> None:
        self._counter = counter
        self._log_interval_seconds = log_interval_seconds
        self._clock = clock
        self._log = log
        self._last_log_at: float | None = None
        self._lock = threading.Lock()

    def report(self, exc: Exception, *, method: str, path: str) -> None:
        # 指标记录每一次失败；日志只保留低敏感度上下文并限频，避免 MQ 故障时刷屏。
        self._counter.inc()
        now = self._clock()
        with self._lock:
            should_log = (
                self._last_log_at is None
                or now - self._last_log_at >= self._log_interval_seconds
            )
            if should_log:
                self._last_log_at = now

        if should_log:
            self._log.warning(
                "traffic recording enqueue failed method=%s path=%s error_type=%s",
                method,
                path,
                type(exc).__name__,
            )


recording_failure_monitor = RecordingFailureMonitor()
