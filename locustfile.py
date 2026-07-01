import os
import redis
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner, WorkerRunner

TARGET_PATH = os.environ.get("TARGET_PATH", "/health")   # 兜底默认，运行时会被 set_path 覆盖


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
        path = r.get("locust:target_path")
        if path:
            environment.runner.send_message("set_path", path.decode())


class WebsiteUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def hit(self):
        self.client.get(TARGET_PATH)
