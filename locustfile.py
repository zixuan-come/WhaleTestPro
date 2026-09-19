import os
import redis
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner, WorkerRunner

TARGET_PATH = os.environ.get("TARGET_PATH", "/health")   # 兜底默认，运行时会被 set_path 覆盖
ACTIVE_RUN_KEY = "locust:active_run"


def _decode(value):
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else str(value)


def _on_set_path(environment, msg, **kwargs):
    global TARGET_PATH
    TARGET_PATH = msg.data


@events.init.add_listener
def _on_init(environment, **kwargs):
    if isinstance(environment.runner, WorkerRunner):
        environment.runner.register_message("set_path", _on_set_path)


@events.test_start.add_listener
def _on_test_start(environment, **kwargs):
    if isinstance(environment.runner, MasterRunner):
        r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
        run_id = _decode(r.get(ACTIVE_RUN_KEY))
        if run_id:
            path = _decode(r.get(f"locust:target_path:{run_id}"))
            if path:
                environment.runner.send_message("set_path", path)


class WebsiteUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def hit(self):
        self.client.get(TARGET_PATH)
