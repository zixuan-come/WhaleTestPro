import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app.models.suite import TestSuite
from app.schemas.suite import SuiteCreate, SuiteUpdate
from app.repositories import suite as suite_repo
from app.services import suite as suite_service


@pytest.fixture
def db():
    """内存数据库测试夹具

    test_suite 有 ForeignKey("project.id")，而 project 又 FK 到 team/users。
    裸 SQL 建表只造物理表、不进 SQLAlchemy metadata，flush 时 ORM 按 FK 排序表会找不到
    注册的 project 表 → NoReferencedTableError。所以必须导入整条 FK 链上的模型后用
    Base.metadata.create_all 建表（沿用 test_p0_security.py 的既有范式）。
    """
    from app.database import Base
    from app.models.project import Project
    # 导入整条 FK 依赖链，让 metadata 认识全部被引用表
    import app.models.team          # noqa: F401  project.team_id -> team.id
    import app.models.user          # noqa: F401  team.owner_id -> users.id
    import app.models.team_member   # noqa: F401
    import app.models.team_invitation   # noqa: F401
    import app.models.team_permission   # noqa: F401
    import app.models.project_member     # noqa: F401
    import app.models.suite         # noqa: F401  test_suite

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    session.add(Project(id=1, name="test project"))
    session.commit()

    yield session
    session.close()


def test_suite_create(db):
    suite = SuiteCreate(
        name="冒烟测试套件",
        description="每日冒烟",
        type="mixed",
        scenario_ids=[1, 2],
        case_ids=[10, 11],
        tags=["smoke"],
    )
    result = suite_repo.db_create(db, suite, project_id=1)

    assert result.id is not None
    assert result.name == "冒烟测试套件"
    assert result.description == "每日冒烟"
    assert result.type == "mixed"
    assert result.scenario_ids == [1, 2]
    assert result.case_ids == [10, 11]
    assert result.tags == ["smoke"]
    assert result.project_id == 1


def test_suite_get(db):
    suite = SuiteCreate(name="suite1", type="case", case_ids=[1, 2])
    created = suite_repo.db_create(db, suite, project_id=1)

    fetched = suite_repo.db_get(db, created.id, project_id=1)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.name == "suite1"


def test_suite_get_enforces_project_isolation(db):
    suite = SuiteCreate(name="suite1", type="case")
    created = suite_repo.db_create(db, suite, project_id=1)

    # 尝试用错误的 project_id 获取
    fetched = suite_repo.db_get(db, created.id, project_id=999)
    assert fetched is None


def test_suite_list(db):
    suite1 = SuiteCreate(name="suite1", type="case")
    suite2 = SuiteCreate(name="suite2", type="scenario")
    suite_repo.db_create(db, suite1, project_id=1)
    suite_repo.db_create(db, suite2, project_id=1)

    results = suite_repo.db_list(db, project_id=1)
    assert len(results) == 2
    assert results[0].name == "suite1"
    assert results[1].name == "suite2"


def test_suite_update(db):
    suite = SuiteCreate(name="old name", type="case", case_ids=[1])
    created = suite_repo.db_create(db, suite, project_id=1)

    update = SuiteUpdate(name="new name", case_ids=[1, 2, 3])
    updated = suite_repo.db_update(db, created.id, project_id=1, suite_update=update)

    assert updated is not None
    assert updated.name == "new name"
    assert updated.case_ids == [1, 2, 3]
    assert updated.type == "case"  # 未更新的字段保持不变


def test_suite_update_enforces_project_isolation(db):
    suite = SuiteCreate(name="suite1", type="case")
    created = suite_repo.db_create(db, suite, project_id=1)

    update = SuiteUpdate(name="new name")
    result = suite_repo.db_update(db, created.id, project_id=999, suite_update=update)

    assert result is None


def test_suite_delete(db):
    suite = SuiteCreate(name="suite1", type="case")
    created = suite_repo.db_create(db, suite, project_id=1)

    success = suite_repo.db_delete(db, created.id, project_id=1)
    assert success is True

    fetched = suite_repo.db_get(db, created.id, project_id=1)
    assert fetched is None


def test_suite_delete_enforces_project_isolation(db):
    suite = SuiteCreate(name="suite1", type="case")
    created = suite_repo.db_create(db, suite, project_id=1)

    success = suite_repo.db_delete(db, created.id, project_id=999)
    assert success is False

    # 套件仍然存在
    fetched = suite_repo.db_get(db, created.id, project_id=1)
    assert fetched is not None


def test_s_get_raises_404_when_not_found(db):
    with pytest.raises(HTTPException) as exc:
        suite_service.s_get(db, 999, project_id=1)
    assert exc.value.status_code == 404


def test_s_update_raises_404_when_not_found(db):
    update = SuiteUpdate(name="new name")
    with pytest.raises(HTTPException) as exc:
        suite_service.s_update(db, 999, project_id=1, suite_update=update)
    assert exc.value.status_code == 404


def test_s_delete_raises_404_when_not_found(db):
    with pytest.raises(HTTPException) as exc:
        suite_service.s_delete(db, 999, project_id=1)
    assert exc.value.status_code == 404


def test_run_suite_raises_404_when_suite_not_found(db):
    with pytest.raises(HTTPException) as exc:
        suite_service.run_suite(db, 999, project_id=1)
    assert exc.value.status_code == 404


# ---------- run_suite 执行逻辑 ----------
# 策略:monkeypatch 掉 execution 层(不真发 HTTP),专注测 suite 自己的编排:
# 三条路径(scenario/case/tags)、去重、汇总统计、总成绩单落库。
# tags 路径曾因调用不存在的 db_list_by_tags 而崩溃 —— 这些测试锁死回归。

from app.repositories import case as case_repo          # noqa: E402
from app.repositories import scenario as scenario_repo  # noqa: E402
from app.repositories import report as report_repo      # noqa: E402
from app.services import execution as execution_service  # noqa: E402
from app.models.report import TestReport as ReportModel  # noqa: E402  (别名避免 pytest 误当测试类收集)


class _FakeCase:
    def __init__(self, id, name, tags=None):
        self.id = id
        self.name = name
        self.tags = tags or []


class _FakeScenario:
    def __init__(self, id, name, case_ids):
        self.id = id
        self.name = name
        self.case_ids = case_ids


def _make_suite(db, **kwargs):
    suite = SuiteCreate(**kwargs)
    return suite_repo.db_create(db, suite, project_id=1)


def test_run_suite_runs_standalone_cases(db, monkeypatch):
    suite = _make_suite(db, name="s", type="case", case_ids=[10, 11])

    monkeypatch.setattr(case_repo, "db_get",
                        lambda db, cid, pid: _FakeCase(cid, f"case{cid}"))
    ran = []
    def fake_run_case(db, cid, env_id, pid):
        ran.append(cid)
        return {"passed": True}
    monkeypatch.setattr(execution_service, "run_case", fake_run_case)

    result = suite_service.run_suite(db, suite.id, project_id=1)

    assert ran == [10, 11]
    assert result["total"] == 2
    assert result["passed"] == 2
    assert result["failed"] == 0
    assert result["pass_rate"] == 100.0


def test_run_suite_reports_missing_case_as_failed(db, monkeypatch):
    suite = _make_suite(db, name="s", type="case", case_ids=[404])

    monkeypatch.setattr(case_repo, "db_get", lambda db, cid, pid: None)

    result = suite_service.run_suite(db, suite.id, project_id=1)

    assert result["total"] == 1
    assert result["failed"] == 1
    assert result["results"][0]["error"] == "用例不存在"


def test_run_suite_runs_scenarios_via_run_chain(db, monkeypatch):
    suite = _make_suite(db, name="s", type="scenario", scenario_ids=[5])

    monkeypatch.setattr(scenario_repo, "db_get",
                        lambda db, sid, pid: _FakeScenario(sid, "scn", [1, 2]))
    monkeypatch.setattr(execution_service, "run_chain",
                        lambda *a, **k: [{"passed": True}, {"passed": True}])

    result = suite_service.run_suite(db, suite.id, project_id=1)

    assert result["scenario_count"] == 1
    assert result["results"][0]["type"] == "scenario"
    assert result["results"][0]["passed"] is True
    assert result["results"][0]["steps"] == 2


def test_run_suite_runs_tagged_cases(db, monkeypatch):
    # 曾崩溃的路径:带 tags 的套件。回归锁。
    suite = _make_suite(db, name="s", type="case", tags=["smoke"])

    all_cases = [
        _FakeCase(1, "a", tags=["smoke"]),
        _FakeCase(2, "b", tags=["slow"]),
        _FakeCase(3, "c", tags=["smoke", "p0"]),
    ]
    monkeypatch.setattr(case_repo, "db_list", lambda db, pid: all_cases)
    ran = []
    monkeypatch.setattr(execution_service, "run_case",
                        lambda db, cid, env_id, pid: ran.append(cid) or {"passed": True})

    result = suite_service.run_suite(db, suite.id, project_id=1)

    # 只跑带 smoke 标签的 1 和 3,不跑 2
    assert sorted(ran) == [1, 3]
    assert result["total"] == 2


def test_run_suite_dedupes_case_across_scenario_and_tags(db, monkeypatch):
    # 用例 1 同时出现在场景步骤、case_ids、tags 里,只应执行一次
    suite = _make_suite(db, name="s", type="mixed",
                        scenario_ids=[5], case_ids=[1], tags=["smoke"])

    monkeypatch.setattr(scenario_repo, "db_get",
                        lambda db, sid, pid: _FakeScenario(sid, "scn", [1]))
    monkeypatch.setattr(execution_service, "run_chain",
                        lambda *a, **k: [{"passed": True}])
    monkeypatch.setattr(case_repo, "db_get",
                        lambda db, cid, pid: _FakeCase(cid, f"case{cid}"))
    monkeypatch.setattr(case_repo, "db_list",
                        lambda db, pid: [_FakeCase(1, "a", tags=["smoke"])])
    ran = []
    monkeypatch.setattr(execution_service, "run_case",
                        lambda db, cid, env_id, pid: ran.append(cid) or {"passed": True})

    result = suite_service.run_suite(db, suite.id, project_id=1)

    # case 1 在场景里跑过,case_ids 和 tags 都应跳过 → run_case 一次都不调
    assert ran == []
    assert result["scenario_count"] == 1


def test_run_suite_writes_summary_report(db, monkeypatch):
    suite = _make_suite(db, name="冒烟", type="case", case_ids=[1, 2])

    monkeypatch.setattr(case_repo, "db_get",
                        lambda db, cid, pid: _FakeCase(cid, f"case{cid}"))
    # 一过一挂 → 整体失败
    monkeypatch.setattr(execution_service, "run_case",
                        lambda db, cid, env_id, pid: {"passed": cid == 1})

    suite_service.run_suite(db, suite.id, project_id=1)

    report = db.query(ReportModel).filter(ReportModel.execution_type == "suite").first()
    assert report is not None
    assert report.suite_id == suite.id
    assert report.suite_name == "冒烟"
    assert report.passed is False            # 有失败项 → 整体失败
    assert report.detail["total"] == 2
    assert report.detail["passed"] == 1


def test_run_suite_summary_report_passes_when_all_pass(db, monkeypatch):
    suite = _make_suite(db, name="全过", type="case", case_ids=[1])

    monkeypatch.setattr(case_repo, "db_get",
                        lambda db, cid, pid: _FakeCase(cid, "c"))
    monkeypatch.setattr(execution_service, "run_case",
                        lambda db, cid, env_id, pid: {"passed": True})

    suite_service.run_suite(db, suite.id, project_id=1)

    report = db.query(ReportModel).filter(ReportModel.execution_type == "suite").first()
    assert report.passed is True
