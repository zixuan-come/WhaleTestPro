"""Retired fields cannot silently change execution scope; upgrades preserve assets."""
import json

import pytest
from sqlalchemy import create_engine, inspect, text

from app.core.migrations import ensure_tags_removed_schema
from tests.test_execution_reports import reports


@pytest.mark.parametrize("path,payload", [
    ("/cases", {"name": "old", "interface_id": 1, "expected_status": 200, "tags": ["smoke"]}),
    ("/suites", {"name": "old", "type": "mixed", "tags": ["smoke"]}),
    ("/schedules", {"name": "old", "cron": "0 2 * * *", "env_id": 1, "tag": "smoke"}),
])
def test_retired_fields_are_rejected_instead_of_running_an_unintended_scope(reports, path, payload):
    client, _, calls = reports
    response = client.post(path, json=payload)
    assert response.status_code == 422
    assert "标签功能已移除" in response.text
    assert not calls


def test_current_api_and_regression_catalog_no_longer_expose_case_or_suite_tags(reports):
    client, _, _ = reports
    for path in ("/cases/1", "/suites/1"):
        response = client.get(path)
        assert response.status_code == 200
        assert "tags" not in response.json()["data"]
    assert all("tags" not in row for row in client.get("/regression/options").json()["data"]["cases"])


def legacy_engine():
    engine = create_engine("sqlite://")
    with engine.begin() as db:
        db.execute(text("CREATE TABLE test_case(id INTEGER PRIMARY KEY, project_id INTEGER, tags JSON)"))
        db.execute(text("CREATE TABLE test_suite(id INTEGER PRIMARY KEY, project_id INTEGER, case_ids JSON, tags JSON)"))
        db.execute(text("CREATE TABLE schedule(id INTEGER PRIMARY KEY, project_id INTEGER, tag TEXT, suite_id INTEGER, selection JSON, notify BOOLEAN, enabled BOOLEAN, sync_status TEXT)"))
        db.execute(text("CREATE TABLE schedule_sync_outbox(schedule_id INTEGER PRIMARY KEY, payload JSON)"))
        for number, project, tags in [(1, 1, ["smoke"]), (2, 1, ["slow"]), (3, 1, ["smoke"]), (4, 2, ["smoke"])]:
            db.execute(text("INSERT INTO test_case VALUES(:id,:project,:tags)"), {"id": number, "project": project, "tags": json.dumps(tags)})
        db.execute(text("INSERT INTO test_suite VALUES(1,1,'[2,1]','[\"smoke\"]')"))
        db.execute(text("INSERT INTO schedule VALUES(1,1,'smoke',NULL,NULL,0,1,'synced'),(2,1,'missing',NULL,NULL,0,1,'synced'),(3,1,NULL,NULL,NULL,0,1,'synced')"))
        db.execute(text("INSERT INTO schedule_sync_outbox VALUES(1,:payload)"), {"payload": json.dumps({"id": 1, "tag": "smoke"})})
    return engine


def test_upgrade_preserves_explicit_order_project_isolation_and_empty_match_safety():
    engine = legacy_engine()
    ensure_tags_removed_schema(engine)
    ensure_tags_removed_schema(engine)
    with engine.connect() as db:
        assert json.loads(db.execute(text("SELECT case_ids FROM test_suite WHERE id=1")).scalar_one()) == [2, 1, 3]
        selection, enabled = db.execute(text("SELECT selection, enabled FROM schedule WHERE id=1")).one()
        assert json.loads(selection) == {"mode": "case", "ids": [1, 3]} and enabled
        selection, enabled = db.execute(text("SELECT selection,enabled FROM schedule WHERE id=2")).one()
        assert (selection is None or json.loads(selection) is None) and not enabled
        assert json.loads(db.execute(text("SELECT selection FROM schedule WHERE id=3")).scalar_one()) == {"mode": "case", "ids": [1, 2, 3]}
        assert json.loads(db.execute(text("SELECT payload FROM schedule_sync_outbox")).scalar_one()) == {"id": 1}
        assert db.execute(text("SELECT COUNT(*) FROM test_case")).scalar_one() == 4
    for table, column in (("test_case", "tags"), ("test_suite", "tags"), ("schedule", "tag")):
        assert column not in {c["name"] for c in inspect(engine).get_columns(table)}
    engine.dispose()


def test_upgrade_refuses_to_truncate_a_legacy_rule_over_the_explicit_selection_limit():
    engine = legacy_engine()
    with engine.begin() as db:
        for number in range(5, 106):
            db.execute(text("INSERT INTO test_case VALUES(:id,1,'[\"smoke\"]')"), {"id": number})
    with pytest.raises(RuntimeError, match="超过 100"):
        ensure_tags_removed_schema(engine)
    assert "tags" in {c["name"] for c in inspect(engine).get_columns("test_case")}
    engine.dispose()
