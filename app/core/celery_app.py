from celery import Celery
from app.core.config import settings
from prometheus_client import start_http_server
from celery.signals import worker_ready

# Register all SQLAlchemy models when Celery starts outside main.py.
import app.models.case
import app.models.demo_order
import app.models.environment
import app.models.interface
import app.models.mock
import app.models.perf
import app.models.project
import app.models.project_member
import app.models.report
import app.models.scenario
import app.models.scenario_report
import app.models.schedule
import app.models.team
import app.models.team_invitation
import app.models.team_member
import app.models.team_permission
import app.models.traffic_record
import app.models.user

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


