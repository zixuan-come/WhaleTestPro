from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "whale_test_pro",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.perf"],  # 让 worker 启动时 import 这个模块，触发 @task 注册
)






