"""Opt-in, real multi-process MySQL locking tests on a disposable server.

Uses the same guarded administrative URL as the invitation regression. Each
test creates/drops ONLY a UUID schema and uses isolated Redis database 9.
No Celery message or load request is ever published.
"""
import multiprocessing as mp
import os
import queue
import time
import unittest
from uuid import uuid4
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


TEST_URL = os.getenv("WHALE_MYSQL_008_TEST_URL", "")
ALLOW = os.getenv("WHALE_MYSQL_008_ALLOW_CREATE_DROP") == "1"
REDIS_URL = "redis://redis:6379/9"


def modules():
    import app.core.celery_app  # Register all mapped FK/relationship targets.
    from app.database import Base
    from app.models.perf import PerfTask
    from app.models.project import Project
    from app.models.team import Team
    from app.models.user import User
    from app.repositories import perf as perf_repo, project as project_repo
    from app.services import perf
    return Base, PerfTask, Project, Team, User, perf_repo, project_repo, perf


def contender(url, task_id, project_id, action, start, result):
    os.environ.update(DATABASE_URL=url, SHADOW_DATABASE_URL=url,
        REDIS_URL=REDIS_URL, SECRET_KEY="synthetic-mysql-race-only",
        LOCUST_CONTROL_TOKEN="synthetic-mysql-race-only")
    _, _, _, _, _, perf_repo, project_repo, perf = modules()
    engine = create_engine(url, hide_parameters=True)
    try:
        with Session(engine) as db:
            # Establish a real MySQL REPEATABLE READ snapshot + stale identity map.
            project_repo.db_get(db, project_id)
            old = perf_repo.db_get(db, task_id, project_id)
            assert old is not None
            old_status = old.status
            assert db.scalar(text("SELECT @@transaction_isolation")) == "REPEATABLE-READ"
            result.put(("primed", old_status))
            assert start.wait(15), "Parent did not release contender"
            if action == "queue":
                row = perf.s_mark_queued(db, task_id, project_id, "race-message")
            elif action == "delete":
                row = project_repo.db_delete(db, project_id, check_perf=perf.assert_project_idle)
            else:
                row = perf.s_run(db, task_id, project_id, "race-message")
            result.put(("returned", None if row is None else getattr(row, "status", "deleted")))
    except Exception as exc:
        result.put(("error", type(exc).__name__))
    finally:
        engine.dispose()


@unittest.skipUnless(TEST_URL and ALLOW, "Requires explicitly enabled disposable MySQL + Redis")
class ProjectPerfMySQLTests(unittest.TestCase):
    def setUp(self):
        self.url = make_url(TEST_URL)
        self.assertEqual(self.url.drivername, "mysql+pymysql")
        self.assertEqual(self.url.database, "mysql")
        self.assertTrue((self.url.host or "").startswith("whaletestpro-migration-008-test-"))
        self.admin = create_engine(self.url, hide_parameters=True)
        self.addCleanup(self.admin.dispose)
        with self.admin.connect() as db:
            self.assertEqual(db.scalar(text("SELECT @@hostname")), "whale-migration-008-test")
            self.assertTrue(db.scalar(text("SELECT VERSION()")).startswith("8.0."))
        self.schema = "whale_perf_race_" + uuid4().hex
        with self.admin.begin() as db:
            db.execute(text(f"CREATE DATABASE `{self.schema}` CHARACTER SET utf8mb4"))
        self.engine = create_engine(self.url.set(database=self.schema), hide_parameters=True)
        self.addCleanup(self.drop_schema)
        os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
        os.environ.setdefault("SHADOW_DATABASE_URL", "sqlite:///:memory:")
        os.environ.setdefault("SECRET_KEY", "synthetic-mysql-race-only")
        Base, PerfTask, Project, Team, User, self.perf_repo, self.project_repo, self.perf = modules()
        for key, value in {"REDIS_URL": REDIS_URL, "LOCUST_CONTROL_TOKEN": "synthetic-mysql-race-only"}.items():
            setting_patch = patch.object(self.perf.settings, key, value)
            setting_patch.start()
            self.addCleanup(setting_patch.stop)
        self.cache = self.perf.redis.from_url(REDIS_URL)
        self.assertIsNone(self.cache.get(self.perf.RUN_LOCK_KEY), "Disposable Redis DB 9 must start idle")
        self.assertIsNone(self.cache.get(self.perf.ACTIVE_RUN_KEY))
        self.addCleanup(self.release_lease)
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            user = User(username="synthetic_race", hashed_password="not-a-real-password")
            db.add(user)
            db.flush()
            team = Team(name="synthetic_race", owner_id=user.id)
            db.add(team)
            db.flush()
            project = Project(name="synthetic_race", team_id=team.id)
            db.add(project)
            db.flush()
            task = PerfTask(name="synthetic_race", project_id=project.id, status="pending",
                target_host="http://never-send.invalid", target_path="/never", users=1, spawn_rate=1, duration=1)
            db.add(task)
            db.commit()
            self.project_id, self.task_id = project.id, task.id

    def release_lease(self):
        run_id = self.perf._run_id(self.project_id, self.task_id)
        self.perf._release_run_lock(self.cache, run_id, self.perf._lease_id(run_id, "race-message"))

    def drop_schema(self):
        self.engine.dispose()
        self.assertRegex(self.schema, r"^whale_perf_race_[0-9a-f]{32}$")
        with self.admin.begin() as db:
            self.assertEqual(db.scalar(text("SELECT @@hostname")), "whale-migration-008-test")
            db.execute(text(f"DROP DATABASE `{self.schema}`"))

    def child(self, action, expected_status="pending"):
        context = mp.get_context("spawn")
        start, result = context.Event(), context.Queue()
        process = context.Process(target=contender, args=(
            self.engine.url.render_as_string(hide_password=False), self.task_id,
            self.project_id, action, start, result))
        process.start()
        self.addCleanup(self.stop_child, process)
        self.assertEqual(result.get(timeout=15), ("primed", expected_status))
        return process, start, result

    @staticmethod
    def stop_child(process):
        process.join(timeout=1)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)

    def wait_for_actual_lock_wait(self):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with self.admin.connect() as db:
                waiting = db.scalar(text("""SELECT COUNT(*)
                    FROM performance_schema.data_lock_waits w
                    JOIN performance_schema.data_locks l
                    ON w.REQUESTING_ENGINE_LOCK_ID=l.ENGINE_LOCK_ID AND w.ENGINE=l.ENGINE
                    WHERE l.OBJECT_SCHEMA=:schema AND l.OBJECT_NAME='project'"""),
                    {"schema": self.schema})
            if waiting:
                return
            time.sleep(0.05)
        self.fail("Contender did not actually wait on a MySQL project row lock")

    def finish_child(self, process, result):
        outcome = result.get(timeout=15)
        process.join(timeout=15)
        self.assertEqual(process.exitcode, 0)
        return outcome

    def test_delete_wins_against_stale_queue_admission(self):
        process, start, result = self.child("queue")
        with Session(self.engine) as db:
            self.project_repo.db_lock_project(db, self.project_id)
            start.set()
            self.wait_for_actual_lock_wait()
            self.project_repo.db_delete(db, self.project_id, check_perf=self.perf.assert_project_idle)
        self.assertEqual(self.finish_child(process, result), ("returned", None))
        self.assertIsNone(self.cache.get(self.perf.RUN_LOCK_KEY))
        with self.engine.connect() as db:
            self.assertEqual(db.scalar(text("SELECT COUNT(*) FROM perf_tasks")), 0)

    def test_queue_wins_against_stale_project_deletion(self):
        process, start, result = self.child("delete")
        with Session(self.engine) as db:
            self.project_repo.db_lock_project(db, self.project_id)
            start.set()
            self.wait_for_actual_lock_wait()
            self.assertEqual(self.perf.s_mark_queued(db, self.task_id, self.project_id, "race-message").status, "queued")
        self.assertEqual(self.finish_child(process, result), ("error", "ProjectPerfBusyError"))
        with self.engine.connect() as db:
            self.assertEqual(db.scalar(text("SELECT COUNT(*) FROM project")), 1)
            self.assertEqual(db.scalar(text("SELECT status FROM perf_tasks")), "queued")
        self.assertEqual(self.cache.get(self.perf.RUN_LOCK_KEY),
                         f"{self.project_id}:{self.task_id}:race-message".encode())

    def test_delayed_worker_cannot_reacquire_lease_after_cancel_and_delete(self):
        with Session(self.engine) as db:
            self.perf.s_mark_queued(db, self.task_id, self.project_id, "race-message")
        process, start, result = self.child("worker", "queued")
        with Session(self.engine) as db:
            self.assertEqual(self.perf.s_cancel(db, self.task_id, self.project_id).status, "cancelled")
            self.project_repo.db_delete(db, self.project_id, check_perf=self.perf.assert_project_idle)
        start.set()
        self.assertEqual(self.finish_child(process, result), ("returned", None))
        self.assertIsNone(self.cache.get(self.perf.RUN_LOCK_KEY))
        self.assertIsNone(self.cache.get(self.perf.ACTIVE_RUN_KEY))


if __name__ == "__main__":
    unittest.main()
