from prometheus_client import Counter, Gauge

regression_pass_rate = Gauge("whale_regression_pass_rate", "回归通过率")
regression_coverage = Gauge("whale_regression_interface_coverage", "回归接口覆盖率")
perf_rps = Gauge("whale_perf_rps", "压测实时 RPS")
perf_fail_ratio = Gauge("whale_perf_fail_ratio", "压测实时失败率")
perf_avg_response_ms = Gauge("whale_perf_avg_response_ms", "压测实时平均响应(ms)")
perf_user_count = Gauge("whale_perf_user_count", "压测当前并发用户数")
perf_stale_tasks_recovered = Counter(
    "whale_perf_stale_tasks_recovered_total",
    "因排队或 Worker 心跳超时而回收的压测任务数",
    ["previous_status"],
)

# 录制失败不能中断业务请求，但也不能静默丢失。该计数器不使用 path 等高基数
# label，避免大量动态 URL 让 Prometheus 时序数量失控。
traffic_record_enqueue_failures = Counter(
    "whale_traffic_record_enqueue_failures_total",
    "流量录制事件投递失败次数",
)

# Consumer metrics count failed attempts and messages, not confirmed lost rows:
# a disconnected COMMIT can have an unknown outcome and must not be retried.
traffic_record_persist_failures = Counter(
    "whale_traffic_record_persist_failures_total", "流量录制消费保存失败尝试次数",
)
traffic_record_persist_retries = Counter(
    "whale_traffic_record_persist_retries_total", "流量录制回滚后发起有限重试次数",
)
traffic_record_persist_terminal_failures = Counter(
    "whale_traffic_record_persist_terminal_failures_total", "流量录制未确认保存且不再重试的消息数",
)
