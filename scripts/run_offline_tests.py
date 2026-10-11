"""Repeatable CI/local regression with synthetic settings and external IO blocked."""
import os
import sys

os.environ.update(DATABASE_URL="sqlite:///:memory:", SHADOW_DATABASE_URL="sqlite:///:memory:",
    SECRET_KEY="isolated-ci-regression-only-not-a-real-credential", REDIS_URL="redis://127.0.0.1:6379/15",
    CELERY_BROKER_URL="memory://", FEISHU_WEBHOOK="", LOCUST_CONTROL_TOKEN="",
    TEST_DATABASE_URL="",
    LOCUST_SKIP_MONKEY_PATCH="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
for key in ("WHALE_MYSQL_008_TEST_URL", "WHALE_MYSQL_008_ALLOW_CREATE_DROP"):
    os.environ.pop(key, None)

import pymysql
import redis
import requests
import pytest

def blocked(*args, **kwargs):
    raise AssertionError("External HTTP, Redis and MySQL are forbidden in offline regression")

pymysql.connect = blocked
redis.Redis.execute_command = blocked
requests.sessions.Session.request = blocked
raise SystemExit(pytest.main((sys.argv[1:] or ["tests"]) + ["-q", "-p", "no:cacheprovider"]))
