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
