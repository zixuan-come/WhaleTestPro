from prometheus_client import Gauge

regression_pass_rate = Gauge("whale_regression_pass_rate", "回归通过率")
regression_coverage = Gauge("whale_regression_interface_coverage", "回归接口覆盖率")
perf_rps = Gauge("whale_perf_rps", "压测实时 RPS")
perf_fail_ratio = Gauge("whale_perf_fail_ratio", "压测实时失败率")
perf_avg_response_ms = Gauge("whale_perf_avg_response_ms", "压测实时平均响应(ms)")
perf_user_count = Gauge("whale_perf_user_count", "压测当前并发用户数")



