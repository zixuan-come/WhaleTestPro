"""Exercise the installed Locust web routes without servers or load traffic."""
import importlib.util
import os
import sys
from pathlib import Path
# TestClient uses real threads; Locust's CLI applies these patches in production.
os.environ.setdefault("LOCUST_SKIP_MONKEY_PATCH", "1")
import gevent
from locust.env import Environment

CONTROL_HEADERS = {"X-Locust-Control-Token": "deadline-test-control-token"}


class Timer:
    def __init__(self, seconds, function, args):
        self.seconds, self.function, self.args = seconds, function, args
        self.killed = False
    def link_exception(self, _callback):
        return self
    def kill(self, **_kwargs):
        self.killed = True
    def fire(self):
        # Deliberately invoke even a cancelled callback to test generation guard.
        self.function(*self.args)


def test_early_stop_cancels_old_deadline_and_cannot_stop_new_run(monkeypatch):
    monkeypatch.setenv("LOCUST_CONTROL_TOKEN", CONTROL_HEADERS["X-Locust-Control-Token"])
    monkeypatch.setattr(sys, "argv", ["locust"])
    spec = importlib.util.spec_from_file_location("isolated_locustfile", Path(__file__).resolve().parents[1] / "locustfile.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    environment = Environment()
    runner = environment.create_local_runner()
    web = environment.create_web_ui("127.0.0.1", 0, delayed_start=True)
    state = {"running": False, "stops": 0}
    def start(*_args):
        state["running"] = True
    def stop():
        state["running"] = False
        state["stops"] += 1
    timers = []
    def later(seconds, function, *args, **_kwargs):
        timer = Timer(seconds, function, args)
        timers.append(timer)
        return timer
    def spawn(function, *args, **_kwargs):
        function(*args)
        return Timer(0, lambda: None, ())
    monkeypatch.setattr(runner, "start", start)
    monkeypatch.setattr(runner, "stop", stop)
    monkeypatch.setattr(gevent, "spawn_later", later)
    monkeypatch.setattr(gevent, "spawn", spawn)
    module._on_init(environment)
    client = web.app.test_client()
    client.environ_base["HTTP_X_LOCUST_CONTROL_TOKEN"] = CONTROL_HEADERS["X-Locust-Control-Token"]
    try:
        payload = {"user_count": "1", "spawn_rate": "1", "host": "http://isolated.invalid"}
        assert client.post("/swarm", data={**payload, "run_time": "10s"}).json["success"]
        assert client.get("/stop").json["success"]
        assert client.post("/swarm", data={**payload, "run_time": "20s"}).json["success"]
        assert [timer.seconds for timer in timers] == [10, 20]
        timers[0].fire()
        assert state["running"] is True
        assert state["stops"] == 1
        assert timers[0].killed is True
        timers[1].fire()
        assert state["running"] is False
        assert state["stops"] == 2
    finally:
        runner.quit()


def test_invalid_deadline_does_not_start_load(monkeypatch):
    monkeypatch.setenv("LOCUST_CONTROL_TOKEN", CONTROL_HEADERS["X-Locust-Control-Token"])
    monkeypatch.setattr(sys, "argv", ["locust"])
    spec = importlib.util.spec_from_file_location("isolated_locustfile", Path(__file__).resolve().parents[1] / "locustfile.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    environment = Environment()
    runner = environment.create_local_runner()
    web = environment.create_web_ui("127.0.0.1", 0, delayed_start=True)
    calls = []
    monkeypatch.setattr(runner, "start", lambda *_: calls.append(True))
    module._on_init(environment)
    try:
        response = web.app.test_client().post("/swarm", headers=CONTROL_HEADERS, data={"user_count": "1", "spawn_rate": "1", "run_time": "bad"})
        assert response.json["success"] is False
        assert calls == []
    finally:
        runner.quit()


def test_real_gevent_deadline_survives_worker_loss_but_not_early_stop(monkeypatch):
    monkeypatch.setenv("LOCUST_CONTROL_TOKEN", CONTROL_HEADERS["X-Locust-Control-Token"])
    monkeypatch.setattr(sys, "argv", ["locust"])
    spec = importlib.util.spec_from_file_location("isolated_locustfile", Path(__file__).resolve().parents[1] / "locustfile.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    environment = Environment()
    runner = environment.create_local_runner()
    web = environment.create_web_ui("127.0.0.1", 0, delayed_start=True)
    state = {"running": False}
    monkeypatch.setattr(runner, "start", lambda *_: state.update(running=True))
    monkeypatch.setattr(runner, "stop", lambda: state.update(running=False))
    module._on_init(environment)
    client = web.app.test_client()
    client.environ_base["HTTP_X_LOCUST_CONTROL_TOKEN"] = CONTROL_HEADERS["X-Locust-Control-Token"]
    payload = {"user_count": "1", "spawn_rate": "1", "host": "http://isolated.invalid"}
    try:
        assert client.post("/swarm", data={**payload, "run_time": "1s"}).json["success"]
        gevent.sleep(0)
        assert client.get("/stop").json["success"]
        assert client.post("/swarm", data={**payload, "run_time": "2s"}).json["success"]
        gevent.sleep(1.1)
        assert state["running"] is True
        # No Celery Worker is driving this timer; Locust itself must stop B.
        gevent.sleep(1.1)
        assert state["running"] is False
    finally:
        client.get("/stop")
        runner.quit()
