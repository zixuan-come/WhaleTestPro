"""Opt-in MySQL 8 regression; never connects to platform databases.

Run in a disposable internal-network MySQL container with hostname
``whale-migration-008-test`` and a tmpfs data directory. The URL must point to
that test container's ``mysql`` administrative database. Each test creates
and drops only its own UUID-named schema containing synthetic rows.
"""
import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.migrations import (
    TEAM_INVITATION_CONSISTENCY_MIGRATION,
    ensure_team_invitation_consistency_schema,
)
from app.models.team import Team  # noqa: F401 -- resolve ORM foreign keys
from app.models.team_invitation import TeamInvitation
from app.models.user import User  # noqa: F401 -- resolve ORM foreign keys


ROOT = Path(__file__).resolve().parents[1]
TEST_URL = os.environ.get("WHALE_MYSQL_008_TEST_URL", "")
ALLOW_TEST_SCHEMAS = os.environ.get("WHALE_MYSQL_008_ALLOW_CREATE_DROP") == "1"


def _script_statements(script):
    """Handle the mysql client's DELIMITER directives without changing SQL."""
    delimiter, pending = ";", []
    for line in script.splitlines():
        stripped = line.strip()
        if not pending and (not stripped or stripped.startswith("--")):
            continue
        if stripped.upper().startswith("DELIMITER "):
            if pending:
                raise AssertionError("SQL delimiter changed within a statement")
            delimiter = stripped.split(None, 1)[1]
            continue
        pending.append(line)
        if "\n".join(pending).rstrip().endswith(delimiter):
            yield "\n".join(pending).rstrip()[:-len(delimiter)]
            pending = []
    if pending:
        raise AssertionError("Unterminated migration SQL")


@unittest.skipUnless(TEST_URL and ALLOW_TEST_SCHEMAS,
                     "MySQL 008 regression requires an explicitly enabled disposable server")
class TeamInvitationMySQLTests(unittest.TestCase):
    def setUp(self):
        self.admin_url = make_url(TEST_URL)
        self.assertEqual(self.admin_url.drivername, "mysql+pymysql")
        self.assertTrue((self.admin_url.host or "").startswith(
            "whaletestpro-migration-008-test-"))
        self.assertEqual(self.admin_url.database, "mysql")
        self.admin = create_engine(self.admin_url, hide_parameters=True)
        self.addCleanup(self.admin.dispose)
        with self.admin.connect() as connection:
            self.assertEqual(connection.scalar(text("SELECT @@hostname")),
                             "whale-migration-008-test")
            self.assertTrue(connection.scalar(text("SELECT VERSION()")).startswith("8.0."))

    @contextmanager
    def schema(self, mode="legacy", old_index=True):
        name = "whale_m008_test_" + uuid4().hex
        self.assertRegex(name, r"^whale_m008_test_[0-9a-f]{32}$")
        with self.admin.begin() as connection:
            connection.execute(text(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4"))
        engine = create_engine(self.admin_url.set(database=name), hide_parameters=True)
        try:
            with engine.begin() as connection:
                # Only parent PKs are needed to reproduce the invitation FKs.
                connection.execute(text("CREATE TABLE users (id INT PRIMARY KEY) ENGINE=InnoDB"))
                connection.execute(text("CREATE TABLE team (id INT PRIMARY KEY) ENGINE=InnoDB"))
                connection.execute(text("INSERT INTO users VALUES (1), (2), (3), (4)"))
                connection.execute(text("INSERT INTO team VALUES (1), (2)"))
            if mode == "model":
                TeamInvitation.__table__.create(engine)
            else:
                unique = ("UNIQUE KEY uq_team_invite_active (team_id, invitee_id, status), "
                          if old_index else "")
                with engine.begin() as connection:
                    connection.execute(text(
                        "CREATE TABLE team_invitation ("
                        "id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, "
                        "team_id INT NOT NULL, inviter_id INT NOT NULL, invitee_id INT NOT NULL, "
                        "role VARCHAR(20) NOT NULL DEFAULT 'member', "
                        "status VARCHAR(20) NOT NULL DEFAULT 'pending', "
                        "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                        "responded_at DATETIME NULL, " + unique +
                        "FOREIGN KEY (team_id) REFERENCES team(id) ON DELETE CASCADE, "
                        "FOREIGN KEY (inviter_id) REFERENCES users(id) ON DELETE CASCADE, "
                        "FOREIGN KEY (invitee_id) REFERENCES users(id) ON DELETE CASCADE"
                        ") ENGINE=InnoDB"))
            with engine.begin() as connection:
                connection.execute(text(
                    "INSERT INTO team_invitation (id, team_id, inviter_id, invitee_id, status) "
                    "VALUES (1,1,1,2,'pending'), (2,1,1,3,'accepted'), (3,1,1,4,'rejected')"))
            if mode in ("runtime", "sql", "model"):
                self.migrate(engine, mode)
            yield engine
        finally:
            engine.dispose()
            # Only this invocation's generated schema on the verified test server.
            self.assertRegex(name, r"^whale_m008_test_[0-9a-f]{32}$")
            with self.admin.begin() as connection:
                self.assertEqual(connection.scalar(text("SELECT @@hostname")),
                                 "whale-migration-008-test")
                connection.execute(text(f"DROP DATABASE `{name}`"))

    def migrate(self, engine, mode):
        if mode == "sql":
            script = (ROOT / "migrations" / "008_team_invitation_consistency.sql").read_text(
                encoding="utf-8")
            with engine.connect() as connection:
                for statement in _script_statements(script):
                    connection.exec_driver_sql(statement)
                connection.commit()
        else:
            ensure_team_invitation_consistency_schema(engine)

    def rows(self, engine):
        with engine.connect() as connection:
            return connection.execute(text(
                "SELECT id, team_id, inviter_id, invitee_id, role, status, created_at, "
                "responded_at FROM team_invitation ORDER BY id")).all()

    def assert_schema(self, engine):
        with engine.connect() as connection:
            extra = connection.scalar(text(
                "SELECT EXTRA FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME='team_invitation' AND COLUMN_NAME='pending_invitee_id'"))
            self.assertEqual(extra, "VIRTUAL GENERATED")
            self.assertEqual(connection.scalar(text("SELECT @@foreign_key_checks")), 1)
            recorded = connection.scalar(text(
                "SELECT COUNT(*) FROM schema_migration WHERE version=:version"),
                {"version": TEAM_INVITATION_CONSISTENCY_MIGRATION})
            self.assertEqual(recorded, 1)
            rules = connection.execute(text(
                "SELECT DELETE_RULE FROM information_schema.REFERENTIAL_CONSTRAINTS "
                "WHERE CONSTRAINT_SCHEMA=DATABASE() AND TABLE_NAME='team_invitation'"
            )).scalars().all()
            self.assertEqual(sorted(rules), ["CASCADE"] * 3)
        indexes = {index["name"] for index in inspect(engine).get_indexes("team_invitation")}
        self.assertIn("uq_team_invitation_pending", indexes)
        self.assertNotIn("uq_team_invite_active", indexes)

    def assert_error(self, engine, sql, code):
        with self.assertRaises(IntegrityError) as caught:
            with engine.begin() as connection:
                connection.execute(text(sql))
        self.assertEqual(caught.exception.orig.args[0], code)

    def test_runtime_upgrade_preserves_rows_and_is_repeatable(self):
        with self.schema() as engine:
            before = self.rows(engine)
            self.migrate(engine, "runtime")
            self.migrate(engine, "runtime")
            self.assertEqual(self.rows(engine), before)
            self.assert_schema(engine)

    def test_standalone_upgrade_preserves_rows_and_is_repeatable(self):
        with self.schema() as engine:
            before = self.rows(engine)
            self.migrate(engine, "sql")
            self.migrate(engine, "sql")
            self.assertEqual(self.rows(engine), before)
            self.assert_schema(engine)

    def test_fresh_model_is_compatible_with_runtime_migration(self):
        with self.schema("model") as engine:
            before = self.rows(engine)
            self.migrate(engine, "runtime")
            self.assertEqual(self.rows(engine), before)
            self.assert_schema(engine)

    def test_pending_uniqueness_and_processed_history(self):
        for mode in ("runtime", "sql", "model"):
            with self.subTest(mode=mode), self.schema(mode) as engine:
                self.assert_error(engine,
                    "INSERT INTO team_invitation (team_id,inviter_id,invitee_id,status) "
                    "VALUES (1,1,2,'pending')", 1062)
                with engine.begin() as connection:
                    connection.execute(text(
                        "INSERT INTO team_invitation (team_id,inviter_id,invitee_id,status) "
                        "VALUES (1,1,3,'accepted'), (1,1,3,'accepted'), "
                        "(1,1,4,'rejected'), (1,1,4,'rejected')"))
                    connection.execute(text("UPDATE team_invitation SET status='accepted' WHERE id=1"))
                    connection.execute(text(
                        "INSERT INTO team_invitation (team_id,inviter_id,invitee_id,status) "
                        "VALUES (1,1,2,'pending')"))
                self.assert_error(engine,
                    "INSERT INTO team_invitation (team_id,inviter_id,invitee_id,status) "
                    "VALUES (1,1,2,'pending')", 1062)
                self.assert_error(engine,
                    "INSERT INTO team_invitation (team_id,inviter_id,invitee_id,status) "
                    "VALUES (1,1,999,'pending')", 1452)
                self.assertEqual(len(self.rows(engine)), 8)
                self.assert_schema(engine)

    def test_all_invitation_cascades_are_preserved(self):
        for mode in ("runtime", "sql", "model"):
            with self.subTest(mode=mode), self.schema(mode) as engine:
                with engine.begin() as connection:
                    connection.execute(text("DELETE FROM users WHERE id=2"))
                self.assertEqual(len(self.rows(engine)), 2)
                with engine.begin() as connection:
                    connection.execute(text("DELETE FROM users WHERE id=1"))
                self.assertEqual(self.rows(engine), [])
                with engine.begin() as connection:
                    connection.execute(text(
                        "INSERT INTO team_invitation (team_id,inviter_id,invitee_id,status) "
                        "VALUES (2,3,4,'pending')"))
                    connection.execute(text("DELETE FROM team WHERE id=2"))
                self.assertEqual(self.rows(engine), [])
                self.assert_schema(engine)

    def test_duplicate_pending_aborts_without_deleting_rows(self):
        for mode in ("runtime", "sql"):
            with self.subTest(mode=mode), self.schema(old_index=False) as engine:
                with engine.begin() as connection:
                    connection.execute(text(
                        "INSERT INTO team_invitation (team_id,inviter_id,invitee_id,status) "
                        "VALUES (1,1,2,'pending')"))
                before = self.rows(engine)
                if mode == "runtime":
                    with self.assertRaisesRegex(RuntimeError, "重复待处理"):
                        self.migrate(engine, mode)
                else:
                    with self.assertRaises(DBAPIError) as caught:
                        self.migrate(engine, mode)
                    self.assertEqual(caught.exception.orig.args[0], 1644)
                self.assertEqual(self.rows(engine), before)
                indexes = {index["name"] for index in inspect(engine).get_indexes("team_invitation")}
                self.assertNotIn("uq_team_invitation_pending", indexes)
                self.assertFalse(inspect(engine).has_table("schema_migration"))

    def test_original_stored_generation_reproduces_mysql_1215(self):
        with self.schema() as engine:
            before = self.rows(engine)
            with self.assertRaises(DBAPIError) as caught:
                with engine.begin() as connection:
                    connection.execute(text(
                        "ALTER TABLE team_invitation ADD COLUMN pending_invitee_id INT "
                        "GENERATED ALWAYS AS (CASE WHEN status='pending' THEN invitee_id "
                        "ELSE NULL END) STORED"))
            self.assertEqual(caught.exception.orig.args[0], 1215)
            self.assertEqual(self.rows(engine), before)
            self.assertNotIn("pending_invitee_id", {
                column["name"] for column in inspect(engine).get_columns("team_invitation")})
