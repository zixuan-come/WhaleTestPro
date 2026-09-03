from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text as sql_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.assertions import run_assertions
from app.services import user as user_service


class _Response:
    elapsed = SimpleNamespace(total_seconds=lambda: 0)


def _db_with_items():
    engine = create_engine("sqlite:///:memory:")
    db = sessionmaker(bind=engine)()
    db.execute(sql_text("create table items (value integer)"))
    db.execute(sql_text("insert into items values (1)"))
    db.commit()
    return db


def test_db_eq_allows_single_select():
    db = _db_with_items()

    result = run_assertions(
        _Response(),
        [{"type": "db_eq", "sql": "SELECT value FROM items", "expected": 1}],
        db,
    )[0]

    assert result["passed"] is True
    assert result["actual"] == 1


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM items",
        "UPDATE items SET value = 2",
        "INSERT INTO items VALUES (2)",
        "DROP TABLE items",
        "SELECT value FROM items; DELETE FROM items",
    ],
)
def test_db_eq_rejects_write_or_multi_statement_sql(sql):
    db = _db_with_items()

    result = run_assertions(
        _Response(),
        [{"type": "db_eq", "sql": sql, "expected": 1}],
        db,
    )[0]

    assert result["passed"] is False
    assert db.execute(sql_text("SELECT count(*) FROM items")).scalar() == 1


def test_register_maps_race_integrity_error_to_conflict(monkeypatch):
    class _DB:
        rolled_back = False

        def rollback(self):
            self.rolled_back = True

    def raise_integrity_error(_db, _user):
        raise IntegrityError("insert", {}, Exception("duplicate"))

    monkeypatch.setattr(user_service.user_repo, "db_get_by_username", lambda _db, _name: None)
    monkeypatch.setattr(user_service.user_repo, "db_create", raise_integrity_error)

    db = _DB()
    with pytest.raises(HTTPException) as exc:
        user_service.s_register(db, SimpleNamespace(username="abcd", password="p" * 8))

    assert exc.value.status_code == 400
    assert db.rolled_back is True