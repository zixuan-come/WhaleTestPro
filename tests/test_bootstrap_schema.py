from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

import app.core.bootstrap as bootstrap
from app.core.bootstrap import ensure_perf_schema, ensure_test_suite_schema, ensure_user_schema
from app.models.user import User


class _FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _FakeMySQLBind:
    dialect = SimpleNamespace(name="mysql")

    def __init__(self, username_length=50, over_limit=0, nullable=False):
        self.username_length = username_length
        self.over_limit = over_limit
        self.nullable = nullable
        self.statements = []

    def begin(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, statement, parameters=None):
        sql = str(statement)
        self.statements.append((sql, parameters))
        if sql.startswith("SELECT COUNT"):
            return _FakeScalarResult(self.over_limit)
        if sql.startswith("ALTER TABLE"):
            self.username_length = 20
            self.nullable = False
        return _FakeScalarResult(None)


class _FakeInspector:
    def __init__(self, bind):
        self.bind = bind

    def has_table(self, table_name):
        return table_name == "users"

    def get_columns(self, table_name):
        assert table_name == "users"
        return [
            {
                "name": "username",
                "type": SimpleNamespace(length=self.bind.username_length),
                "nullable": self.bind.nullable,
            }
        ]


def test_ensure_perf_schema_adds_missing_observability_columns():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE perf_tasks (id INTEGER PRIMARY KEY, name VARCHAR(100))"))

    db = sessionmaker(bind=engine)()
    try:
        ensure_perf_schema(db)
        columns = {column["name"] for column in inspect(engine).get_columns("perf_tasks")}
        assert {
            "p95_response_ms",
            "p99_response_ms",
            "request_stats",
            "error_summary",
            "history_samples",
        } <= columns
    finally:
        db.close()


def test_ensure_test_suite_schema_upgrades_main_and_shadow_idempotently():
    engines = [create_engine("sqlite:///:memory:"), create_engine("sqlite:///:memory:")]
    for engine in engines:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE project (id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE schedule (id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE test_report (id INTEGER PRIMARY KEY)"))

        ensure_test_suite_schema(engine)
        ensure_test_suite_schema(engine)

        inspector = inspect(engine)
        assert inspector.has_table("test_suite")
        assert {"suite_id"} <= {
            column["name"] for column in inspector.get_columns("schedule")
        }
        assert {"suite_id", "suite_name", "execution_type"} <= {
            column["name"] for column in inspector.get_columns("test_report")
        }
        assert any(
            index["column_names"] == ["suite_id"]
            for index in inspector.get_indexes("schedule")
        )
        assert any(
            index["column_names"] == ["suite_id"]
            for index in inspector.get_indexes("test_report")
        )


def test_user_model_username_column_matches_domain_limit():
    assert User.__table__.c.username.type.length == 20


def test_ensure_user_schema_upgrades_main_and_shadow_idempotently(monkeypatch):
    monkeypatch.setattr(bootstrap, "inspect", lambda bind: _FakeInspector(bind))
    engines = [_FakeMySQLBind(), _FakeMySQLBind()]

    for engine in engines:
        ensure_user_schema(engine)
        ensure_user_schema(engine)

        alter_statements = [
            sql for sql, _ in engine.statements if sql.startswith("ALTER TABLE")
        ]
        assert engine.username_length == 20
        assert alter_statements == [
            "ALTER TABLE `users` MODIFY COLUMN `username` VARCHAR(20) NOT NULL"
        ]


def test_ensure_user_schema_blocks_overlength_legacy_data(monkeypatch):
    monkeypatch.setattr(bootstrap, "inspect", lambda bind: _FakeInspector(bind))
    engine = _FakeMySQLBind(over_limit=1)

    with pytest.raises(RuntimeError, match="存在 1 个超过 20 字符的用户名"):
        ensure_user_schema(engine)

    assert not any(sql.startswith("ALTER TABLE") for sql, _ in engine.statements)
