from celery import Celery
from app.core.config import settings
from prometheus_client import start_http_server
from celery.signals import worker_ready

celery_app = Celery(
    "whale_test_pro",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.perf", "app.tasks.schedule", "app.tasks.traffic"],  # 让 worker 启动时 import 这个模块，触发 @task 注册
)

celery_app.conf.redbeat_redis_url = settings.REDIS_URL
celery_app.conf.beat_scheduler = "redbeat.RedBeatScheduler"


@worker_ready.connect
def _start_metrics_server(**kwargs):
    start_http_server(8002)  # worker 进程的 /metrics 窗口,挂 8002


