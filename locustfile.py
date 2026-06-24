import os
from locust import HttpUser, task, between

TARGET_PATH = os.environ.get("TARGET_PATH", "/health")

class WebsiteUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def hit(self):
        self.client.get(TARGET_PATH)





