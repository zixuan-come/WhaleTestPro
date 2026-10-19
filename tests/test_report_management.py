"""Real routes/authorization against isolated SQLite; no user reports are touched."""
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, inspect, text

from tests.test_execution_reports import reports  # Isolated assets and synthetic HTTP transport.
from app.core.authentication import get_current_user
from app.core.migrations import ensure_report_folder_schema
from app.models.user import User
from app.models.team_member import TeamMember
from app.models.team_permission import TeamPermission
from app.models.execution_report import ExecutionReport
from app.models.report import TestReport as Report
from app.models.report_folder import ReportFolder, ReportFolderItem
from app.models.scenario_report import ScenarioReport, ScenarioReportStep
from app.models.case import Case
from app.models.scenario import Scenario
from app.models.suite import TestSuite as Suite
from app.routers import report
from app.repositories import project as project_repository


@pytest.fixture
def managed(reports):
    client, db, _ = reports
    db.add_all([User(id=i, username=f"report-role-{i}", hashed_password="unused") for i in (2, 3, 4)])
    db.flush()
    db.add_all([TeamMember(team_id=1, user_id=i, role=role) for i, role in ((1, "owner"), (2, "admin"), (3, "member"))])
    db.commit()
    actor = SimpleNamespace(id=1)
    for route in report.router.routes:
        for dependency in route.dependant.dependencies:
            if dependency.name == "context":
                client.app.dependency_overrides.pop(dependency.call, None)
    client.app.dependency_overrides[get_current_user] = lambda: db.get(User, actor.id)
    client.headers["X-Project-Id"] = "1"
    return client, db, actor


def data(response, status=200):
    assert response.status_code == status, response.text
    return response.json()["data"]


def run(db, project=1, *, parent=None, state="completed", kind="case"):
    row = ExecutionReport(project_id=project, kind=kind, name="测试报告", parent_id=parent,
        passed=None if state == "running" else True, status=state, created_at=datetime.utcnow())
    db.add(row); db.commit()
    return row.id


def test_folders_rename_duplicates_delete_keeps_reports_and_counts(managed):
    client, db, _ = managed
    a, b = run(db), run(db, kind="scenario")
    folder = data(client.post("/reports/folders", json={"name": "  2026-10-20-张三  "}), 201)
    assert folder["name"] == "2026-10-20-张三"
    assert client.post("/reports/folders", json={"name": folder["name"]}).status_code == 409
    f = folder["id"]
    assert data(client.put(f"/reports/folders/{f}", json={"name": "本轮验收"}))["name"] == "本轮验收"
    assert data(client.post("/reports/executions/move", json={"report_ids": [f"run-{a}", f"run-{b}"], "folder_id": f}))["moved"] == 2
    folders = data(client.get("/reports/folders"))
    assert folders["can_manage"] and folders["total"] == 2 and folders["unfiled"] == 0
    assert folders["items"][0]["count"] == 2
    page = data(client.get("/reports/executions", params={"kind": "all", "folder_id": f}))
    assert page["total"] == 2 and {item["folder_id"] for item in page["items"]} == {f}
    assert data(client.get("/reports/executions", params={"kind": "case", "folder_id": f}))["total"] == 1
    assert data(client.delete(f"/reports/folders/{f}"))["unfiled"] == 2
    assert db.query(ExecutionReport).count() == 2
    assert data(client.get("/reports/executions", params={"kind": "all", "folder_id": 0}))["total"] == 2


def test_mixed_legacy_reports_can_move_clear_and_delete(managed):
    client, db, _ = managed
    modern = run(db)
    legacy = Report(project_id=1, case_id=1, passed=False, detail={})
    old_scene = ScenarioReport(project_id=1, scenario_id=1, scenario_name="旧场景", passed=True,
        total_steps=1, passed_steps=1, failed_steps=0, duration_ms=3, created_at=datetime.utcnow())
    db.add_all([legacy, old_scene]); db.flush()
    db.add(ScenarioReportStep(report_id=old_scene.id, sequence=1, case_id=1, passed=True, duration_ms=3))
    db.commit()
    refs = [f"run-{modern}", f"legacy-{legacy.id}", f"scenario-{old_scene.id}"]
    f = data(client.post("/reports/folders", json={"name": "历史验收"}), 201)["id"]
    data(client.post("/reports/executions/move", json={"report_ids": refs, "folder_id": f}))
    assert data(client.get("/reports/executions", params={"kind": "all", "folder_id": f}))["total"] == 3
    data(client.post("/reports/executions/move", json={"report_ids": [refs[0]], "folder_id": None}))
    assert data(client.get("/reports/folders"))["unfiled"] == 1
    assert data(client.post("/reports/executions/delete", json={"report_ids": refs}))["deleted"] == 3
    assert db.query(ScenarioReportStep).count() == db.query(ReportFolderItem).count() == 0
    assert data(client.get("/reports/folders"))["total"] == 0


def test_delete_execution_tree_removes_owned_evidence_and_preserves_assets_and_other_projects(managed):
    client, db, _ = managed
    data(client.post("/suites/1/run?env_id=1"))
    root = data(client.get("/reports/executions?kind=suite"))["items"][0]["id"]
    root_id = int(root.split("-")[1])
    child_id = db.query(ExecutionReport.id).filter_by(parent_id=root_id).first()[0]
    run(db, parent=child_id)  # Prove recursive cleanup, not only immediate children.
    foreign = run(db, project=2, parent=root_id)
    asset_counts = [db.query(model).count() for model in (Case, Scenario, Suite)]
    assert data(client.delete(f"/reports/executions/{root}"))["deleted"] == 1
    assert db.query(ExecutionReport).count() == 1 and db.get(ExecutionReport, foreign) is not None
    assert db.query(Report).count() == db.query(ScenarioReport).count() == db.query(ScenarioReportStep).count() == 0
    assert asset_counts == [db.query(model).count() for model in (Case, Scenario, Suite)]
    assert client.get(f"/reports/executions/{root}").status_code == 404


def test_atomic_batch_rejects_running_foreign_missing_or_child_selections(managed):
    client, db, _ = managed
    ready, active, foreign = run(db), run(db, state="running"), run(db, project=2)
    child = run(db, parent=ready)
    folder = data(client.post("/reports/folders", json={"name": "归档"}), 201)["id"]
    for bad, status in ((active, 409), (foreign, 404), (99999, 404), (child, 404)):
        response = client.post("/reports/executions/delete", json={"report_ids": [f"run-{ready}", f"run-{bad}"]})
        assert response.status_code == status, response.text
        assert db.get(ExecutionReport, ready) is not None
    for bad in (foreign, 99999, child):
        assert client.post("/reports/executions/move", json={"report_ids": [f"run-{ready}", f"run-{bad}"], "folder_id": folder}).status_code == 404
        assert db.query(ReportFolderItem).count() == 0
    run(db, parent=ready, state="running")
    assert client.delete(f"/reports/executions/run-{ready}").status_code == 409


def test_project_and_role_permissions_apply_to_every_mutation(managed):
    client, db, actor = managed
    number = run(db)
    f = data(client.post("/reports/folders", json={"name": "权限验收"}), 201)["id"]
    requests = [("post", "/reports/folders", {"name": "新目录"}),
        ("put", f"/reports/folders/{f}", {"name": "改名"}), ("delete", f"/reports/folders/{f}", None),
        ("post", "/reports/executions/move", {"report_ids": [f"run-{number}"], "folder_id": f}),
        ("post", "/reports/executions/delete", {"report_ids": [f"run-{number}"]}),
        ("delete", f"/reports/executions/run-{number}", None)]
    actor.id = 3
    assert data(client.get("/reports/folders"))["can_manage"] is False
    for method, url, payload in requests:
        assert client.request(method, url, **({"json": payload} if payload else {})).status_code == 403
    db.add(TeamPermission(team_id=1, role="member", permission="report.write", enabled=True)); db.commit()
    assert data(client.get("/reports/folders"))["can_manage"] is True
    assert client.post("/reports/executions/move", json={"report_ids": [f"run-{number}"], "folder_id": f}).status_code == 200
    actor.id = 2
    assert data(client.get("/reports/folders"))["can_manage"] is True
    client.headers["X-Project-Id"] = "2"
    for method, url, payload in requests[1:]:
        assert client.request(method, url, **({"json": payload} if payload else {})).status_code == 404
    actor.id = 4
    assert client.get("/reports/folders").status_code == 404


@pytest.mark.parametrize("payload", [{"name": " "}, {"name": "x" * 101}, {"name": "x", "project_id": 2}])
def test_invalid_folder_input_rejected(managed, payload):
    assert managed[0].post("/reports/folders", json=payload).status_code == 422


def test_selection_validation_and_folder_filter_are_scoped(managed):
    client, _, _ = managed
    for refs in ([], ["run-0"], ["bad"], ["run-1"] * 501):
        assert client.post("/reports/executions/delete", json={"report_ids": refs}).status_code == 422
    assert client.get("/reports/executions?folder_id=999").status_code == 404
    assert client.get("/reports/executions?folder_id=-1").status_code == 422


def test_migration_is_additive_and_repeatable():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE project (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE test_report (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO test_report VALUES (7)"))
    ensure_report_folder_schema(engine); ensure_report_folder_schema(engine)
    assert {"report_folder", "report_folder_item"}.issubset(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert connection.execute(text("SELECT id FROM test_report")).all() == [(7,)]
        assert connection.execute(text("SELECT COUNT(*) FROM report_folder_item")).scalar_one() == 0
    engine.dispose()


def test_project_delete_cleans_organization_without_blocking_foreign_keys(managed):
    client, db, _ = managed
    number = run(db)
    folder = data(client.post("/reports/folders", json={"name": "项目内目录"}), 201)["id"]
    data(client.post("/reports/executions/move", json={"report_ids": [f"run-{number}"], "folder_id": folder}))
    assert project_repository.db_delete(db, 1) is not None
    assert db.query(ReportFolder).count() == db.query(ReportFolderItem).count() == 0
