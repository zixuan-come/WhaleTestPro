"""User-authored SQL must use a restricted, separate test database."""
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core import assertions, sql_database, sql_runner
from app.core.celery_app import celery_app  # Registers all related models.
from app.core.config import settings
from app.database import Base
from app.models.user import User


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(username="p1-owner", hashed_password="fake-secret"))
        session.commit()
        yield session
    engine.dispose()


def test_sql_disabled_never_touches_platform_db(db, monkeypatch):
    monkeypatch.setattr(settings, "TEST_DATABASE_URL", None)
    before = db.query(User).first().hashed_password
    with pytest.raises(ValueError, match="平台业务表"):
        sql_runner.run_sql(db, ["UPDATE `users` SET hashed_password='changed' WHERE id=1"])
    result = assertions.run_assertions(None, [{"type": "db_eq", "sql": "SELECT hashed_password FROM users", "expected": "fake-secret"}], db)[0]
    assert result["passed"] is False
    assert "fake-secret" not in result["actual"]
    assert db.query(User).first().hashed_password == before


@pytest.mark.parametrize("url", [
    "mysql+pymysql://root:dummy@another-host/tested",
    "sqlite:///:memory:",
])
def test_sql_rejects_unsafe_connection(url, monkeypatch):
    monkeypatch.setattr(settings, "TEST_DATABASE_URL", url)
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite:///:memory:")
    with pytest.raises(ValueError):
        sql_database._validated_url()


def test_sql_batch_is_atomic_and_uses_separate_database(db, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE items(value INTEGER)"))
            connection.execute(text("INSERT INTO items VALUES (1)"))

        @contextmanager
        def tested_session():
            with Session(engine) as tested:
                yield tested

        monkeypatch.setattr(sql_runner, "test_sql_session", tested_session)
        monkeypatch.setattr(assertions, "test_sql_session", tested_session)
        sql_runner.run_sql(db, ["UPDATE items SET value=2 WHERE value=1"])
        result = assertions.run_assertions(None, [{"type": "db_eq", "sql": "SELECT value FROM items", "expected": 2}], db)[0]
        assert result["passed"]
        with pytest.raises(Exception):
            sql_runner.run_sql(db, ["UPDATE items SET value=3 WHERE value=2", "INSERT INTO missing VALUES (1)"])
        with engine.connect() as connection:
            assert connection.execute(text("SELECT value FROM items")).scalar() == 2
        assert db.query(User).count() == 1
    finally:
        engine.dispose()


@pytest.mark.parametrize("grant", [
    "GRANT ALL PRIVILEGES ON *.* TO `test`@`%`",
    "GRANT SELECT ON `whale_test_pro`.* TO `test`@`%`",
    "GRANT CREATE ON `tested`.* TO `test`@`%`",
    "GRANT SELECT ON `tested`.* TO `test`@`%` WITH GRANT OPTION",
    "GRANT `admin_role`@`%` TO `test`@`%`",
])
def test_test_sql_account_rejects_excessive_grants(grant):
    with pytest.raises(ValueError):
        sql_database._validate_mysql_grants([grant], "tested")


def test_test_sql_account_accepts_only_own_schema_dml():
    sql_database._validate_mysql_grants([
        "GRANT USAGE ON *.* TO `test`@`%`",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON `tested`.* TO `test`@`%`",
    ], "tested")


@pytest.mark.parametrize(("schema", "database"), [
    ("whale_test_pr_", "whale_test_pr_"),
    ("tested%", "tested%"),
    (r"tested\\_db", r"tested\_db"),
    ("tested\\", "tested"),
    (r"tested\q", "testedq"),
])
def test_test_sql_account_rejects_wildcard_or_ambiguous_schema(schema, database):
    grant = f"GRANT SELECT ON `{schema}`.* TO `test`@`%`"
    with pytest.raises(ValueError):
        sql_database._validate_mysql_grants([grant], database)


def test_test_sql_account_accepts_explicitly_escaped_literal_schema():
    sql_database._validate_mysql_grants([
        r"GRANT SELECT, INSERT, UPDATE, DELETE ON `tested\_db`.* TO `test`@`%`",
    ], "tested_db")


@pytest.mark.parametrize("platform_url", [
    "sqlite:///file:whale_sql_review?mode=memory&cache=shared&uri=true",
    "mysql+pymysql://platform:dummy@localhost/platform",
])
def test_sql_rejects_sqlite_uri_alias_even_if_platform_backend_differs(monkeypatch, platform_url):
    monkeypatch.setattr(settings, "DATABASE_URL", platform_url)
    monkeypatch.setattr(settings, "TEST_DATABASE_URL", "sqlite:///file:%77hale_sql_review?mode=memory&cache=shared&uri=true")
    with pytest.raises(ValueError, match="SQLite URI"):
        sql_database._validated_url()


def test_sql_rejects_plain_test_file_when_platform_uses_uri(monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite:///file:platform.db?uri=true")
    monkeypatch.setattr(settings, "TEST_DATABASE_URL", "sqlite:///tested.db")
    with pytest.raises(ValueError, match="SQLite URI"):
        sql_database._validated_url()
