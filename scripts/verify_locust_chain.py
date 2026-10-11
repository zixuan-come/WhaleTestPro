"""Opt-in, bounded distributed verification against a loopback synthetic service.

Run in an isolated container with a dedicated Redis, never the platform Redis.
WHALE_LOAD_VERIFY_ALLOW=isolated-fixture is mandatory. No real credentials/data.
"""
from gevent import monkey
monkey.patch_all()
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import gevent
import redis
import requests
from flask import Flask, jsonify, request
from gevent.pywsgi import WSGIServer

if os.environ.get("WHALE_LOAD_VERIFY_ALLOW") != "isolated-fixture":
    raise SystemExit("Explicit isolated fixture opt-in required")
if os.environ.get("REDIS_URL") != "redis://load-check-redis:6379/0":
    raise SystemExit("Refusing any Redis other than the dedicated fixture")

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "synthetic-isolated-locust-control"
headers = {"X-Locust-Control-Token": TOKEN}
service = Flask("synthetic-load-fixture")
calls, owners, order_owners = [], {}, {}

@service.route("/login", methods=["POST"])
def login():
    body = request.get_json()
    owner = body["owner"]
    token = f"fixture-{owner}"
    owners[token] = owner
    calls.append(("POST", "/login", owner))
    return jsonify(token=token)

@service.route("/orders", methods=["POST"])
def create_order():
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    body = request.get_json()
    assert owners[token] == body["owner"]
    identity = f'{body["owner"]}-{body["iteration"]}'
    assert identity not in order_owners
    order_owners[identity] = body["owner"]
    calls.append(("POST", "/orders", body["owner"]))
    return jsonify(id=identity, code=0), 201

@service.route("/orders/<identity>", methods=["GET", "DELETE"])
def order(identity):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    assert owners[token] == order_owners[identity]
    calls.append((request.method, "/orders/:id", owners[token]))
    if request.method == "DELETE":
        del order_owners[identity]
    return jsonify(code=0)

@service.route("/form", methods=["POST"])
def form():
    assert request.form["owner"] in owners.values()
    assert request.form["iteration"].isdigit()
    calls.append(("POST", "/form", request.form["owner"]))
    return jsonify(code=0)

@service.route("/raw", methods=["PUT"])
def raw():
    assert request.headers["Content-Type"] == "application/xml"
    assert request.get_data(as_text=True).startswith("<owner>")
    calls.append(("PUT", "/raw", "synthetic"))
    return jsonify(code=0)

@service.route("/other", methods=["PATCH", "HEAD", "OPTIONS"])
def other():
    calls.append((request.method, "/other", "synthetic"))
    return jsonify(code=0)

@service.route("/business-fail", methods=["POST"])
def business_fail():
    calls.append(("POST", "/business-fail", "synthetic"))
    return jsonify(code=99)


server = WSGIServer(("127.0.0.1", 0), service, log=None)
server.start()
host = f"http://127.0.0.1:{server.server_port}"
cache = redis.from_url(os.environ["REDIS_URL"])
assert cache.dbsize() == 0, "Fixture Redis must start empty"
environment = dict(os.environ, LOCUST_CONTROL_TOKEN=TOKEN)
processes = []

def read(path):
    response = requests.get("http://127.0.0.1:8089" + path, headers=headers, timeout=5)
    response.raise_for_status()
    return response.json()

def wait_ready():
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        try:
            stats = read("/stats/requests")
            if stats.get("workers"):
                return
        except requests.RequestException:
            pass
        if any(process.poll() is not None for process in processes):
            raise AssertionError("Locust subprocess exited before readiness")
        gevent.sleep(0.2)
    raise AssertionError("Locust master/worker readiness timeout")

def run_plan(config, generation):
    run, lease = "1:1", f"1:1:{generation}"
    cache.set("locust:run_lock", lease, ex=30)
    cache.set("locust:active_run", run, ex=30)
    cache.set(f"locust:target_path:{run}", json.dumps({"lease": lease, "deadline": time.time() + 3,
                                                      "target_host": host, "load_config": config}), ex=30)
    response = requests.post("http://127.0.0.1:8089/swarm", headers=headers,
        data={"user_count": 2, "spawn_rate": 2, "host": host, "run_time": "3s"}, timeout=10)
    response.raise_for_status()
    assert response.json()["success"]
    gevent.sleep(3.6)
    requests.get("http://127.0.0.1:8089/stop", headers=headers, timeout=10).raise_for_status()
    gevent.sleep(0.5)
    iterations = read("/whale/iterations")
    stats = read("/stats/requests")
    assert iterations["lease"] == lease and iterations["configuration_failures"] == 0
    assert iterations["iterations"] > 0
    before = len(calls)
    gevent.sleep(0.3)
    assert len(calls) == before, "Traffic continued after stop"
    return iterations, stats

try:
    base = [sys.executable, "-m", "locust", "-f", str(ROOT / "locustfile.py"), "--loglevel", "WARNING"]
    for flags in [["--master", "--master-bind-host", "127.0.0.1", "--web-host", "127.0.0.1"],
                  ["--worker", "--master-host", "127.0.0.1"]]:
        processes.append(subprocess.Popen(base + flags, cwd=ROOT, env=environment,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    wait_ready()
    auth = {"Authorization": "Bearer ${token}"}
    config = {"mode": "chain", "wait_seconds": 0.1, "timeout_seconds": 2, "steps": [
        {"method": "POST", "path": "/login", "body_type": "json", "body": {"owner": "${_vu_id}"}, "extract_rules": {"token": "$.token"}},
        {"method": "POST", "path": "/orders", "headers": auth, "body_type": "json", "body": {"owner": "${_vu_id}", "iteration": "${_iteration}"}, "expected_status": 201, "extract_rules": {"order": "$.id"}},
        {"path": "/orders/${order}", "headers": auth, "assertions": [{"type": "json_eq", "path": "$.code", "expected": 0}]},
        {"method": "POST", "path": "/form", "body_type": "form", "body": {"owner": "${_vu_id}", "iteration": "${_iteration}"}},
        {"method": "PUT", "path": "/raw", "body_type": "raw", "body": "<owner>${_vu_id}</owner>", "headers": {"Content-Type": "application/xml"}},
        {"method": "PATCH", "path": "/other"}, {"method": "DELETE", "path": "/orders/${order}", "headers": auth},
        {"method": "HEAD", "path": "/other"}, {"method": "OPTIONS", "path": "/other"}]}
    iterations, stats = run_plan(config, "success-generation")
    assert iterations["failures"] == 0 and stats["fail_ratio"] == 0
    assert len(set(row[2] for row in calls if row[1] == "/login")) == 2
    assert {row[0] for row in calls} == {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
    assert len([row for row in stats["stats"] if row["name"] != "Aggregated"]) == 9
    successful_http_count = len(calls)
    bad = {"mode": "chain", "wait_seconds": 0.1, "steps": [
        {"method": "POST", "path": "/business-fail", "assertions": [{"type": "json_eq", "path": "$.code", "expected": 0}]},
        {"path": "/never-send"}]}
    failed_iterations, failed_stats = run_plan(bad, "failure-generation")
    assert failed_iterations["failures"] == failed_iterations["iterations"]
    assert failed_stats["fail_ratio"] == 1
    assert all(row[1] == "/business-fail" for row in calls[successful_http_count:])
    # Missing plan must be observable and must never silently run the default GET.
    bad_lease = "1:1:missing-generation"
    cache.set("locust:run_lock", bad_lease, ex=30)
    cache.delete("locust:target_path:1:1")
    before_bad = len(calls)
    response = requests.post("http://127.0.0.1:8089/swarm", headers=headers,
        data={"user_count": 2, "spawn_rate": 2, "host": host, "run_time": "2s"}, timeout=10)
    response.raise_for_status()
    gevent.sleep(2.5)
    bad_stats = read("/whale/iterations")
    assert bad_stats["lease"] == bad_lease and bad_stats["configuration_failures"] == 2
    assert len(calls) == before_bad
    print(json.dumps({"status": "passed", "users": 2, "duration_each_seconds": 3,
        "successful_iterations": iterations["iterations"], "successful_http_requests": successful_http_count,
        "failed_iterations": failed_iterations["iterations"], "http_methods": sorted({row[0] for row in calls}),
        "stop_verified": True, "missing_plan_fail_closed": True, "fixture_only": True}, ensure_ascii=False))
finally:
    for process in reversed(processes):
        process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    server.stop()
    cache.delete("locust:run_lock", "locust:active_run", "locust:target_path:1:1")
