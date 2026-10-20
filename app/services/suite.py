from datetime import datetime
from time import perf_counter
from types import SimpleNamespace
from copy import deepcopy
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.repositories import suite as suite_repo
from app.repositories import case as case_repo
from app.repositories import scenario as scenario_repo
from app.repositories import environment as environment_repo
from app.repositories import report as report_repo
from app.services import execution
from app.schemas.suite import SuiteCreate, SuiteUpdate
from app.services.execution_tracking import tracked
from app.core.scenario_steps import equivalent_case_ids, standalone_case_options
from app.models.case import Case
from app.models.interface import Interface


def s_create(db: Session, suite: SuiteCreate, project_id: int):
    """创建测试套件"""
    return suite_repo.db_create(db, suite, project_id)


def s_get(db: Session, suite_id: int, project_id: int):
    """获取测试套件"""
    suite = suite_repo.db_get(db, suite_id, project_id)
    if not suite:
        raise HTTPException(status_code=404, detail="测试套件不存在")
    return suite


def s_list(db: Session, project_id: int, skip: int = 0, limit: int = 100):
    """获取测试套件列表"""
    return suite_repo.db_list(db, project_id, skip, limit)


def s_update(db: Session, suite_id: int, project_id: int, suite_update: SuiteUpdate):
    """更新测试套件"""
    suite = suite_repo.db_update(db, suite_id, project_id, suite_update)
    if not suite:
        raise HTTPException(status_code=404, detail="测试套件不存在")
    return suite


def s_delete(db: Session, suite_id: int, project_id: int):
    """删除测试套件"""
    try:
        success = suite_repo.db_delete(db, suite_id, project_id)
    except suite_repo.SuiteInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not success:
        raise HTTPException(status_code=404, detail="测试套件不存在")
    return {"message": "删除成功"}


@tracked("suite")
def run_suite(db: Session, suite_id: int, project_id: int, env_id: int | None = None):
    """
    运行测试套件

    执行流程:
    1. 运行 scenario_ids 中的场景 (链式传参)
    2. 运行 case_ids 中的独立用例
    3. 汇总结果并写入报告
    """
    suite = suite_repo.db_get(db, suite_id, project_id)
    if not suite:
        raise HTTPException(status_code=404, detail="测试套件不存在")

    if env_id is not None and environment_repo.db_get(db, env_id, project_id) is None:
        raise ValueError(f"环境 id={env_id} 不存在或不属于当前项目")

    # Child-report commits expire ORM objects; another request may delete or
    # edit the suite while HTTP calls run. Execute a fixed value snapshot.
    suite = SimpleNamespace(
        id=suite.id, name=suite.name, type=suite.type,
        scenario_ids=tuple(suite.scenario_ids or ()),
        case_ids=tuple(suite.case_ids or ()),
    )
    started_at = datetime.utcnow()
    started = perf_counter()

    results = []
    executed_case_ids = set()  # 去重：避免场景和独立用例重复执行

    # 1. 运行场景
    for scenario_id in suite.scenario_ids or []:
        scenario = scenario_repo.db_get(db, scenario_id, project_id)
        if not scenario:
            results.append({
                "type": "scenario",
                "id": scenario_id,
                "name": None,
                "passed": False,
                "error": "场景不存在",
            })
            continue

        # Child execution commits expire ORM rows; the source may be edited or
        # deleted while HTTP is in flight. Keep the values this execution owns.
        scenario = SimpleNamespace(
            id=scenario_id, name=scenario.name,
            case_ids=tuple(scenario.case_ids or ()),
            steps=deepcopy(getattr(scenario, 'steps', None)),
        )

        # run_chain 会写场景报告
        try:
            chain_results = execution.run_chain(
                db,
                scenario.case_ids,
                env_id,
                project_id,
                scenario_id=scenario.id,
                scenario_name=scenario.name,
                **({'steps': scenario.steps} if scenario.steps is not None else {}),
            )
        except Exception as exc:
            db.rollback()
            results.append({"type": "scenario", "id": scenario.id, "name": scenario.name,
                            "passed": False, "error": f"执行异常（{type(exc).__name__}）"})
            continue

        passed = bool(chain_results) and all(r["passed"] for r in chain_results)
        results.append({
            "type": "scenario",
            "id": scenario.id,
            "name": scenario.name,
            "passed": passed,
            "steps": len(chain_results),
            "detail": chain_results,
        })

        # 记录已执行的用例（场景中的步骤）
        if scenario.steps is None:
            executed_case_ids.update(number for number in scenario.case_ids
                if not standalone_case_options(case_repo.db_get(db, number, project_id)))
        else:
            cases = {row.id: row for row in db.query(Case).filter_by(project_id=project_id).all()}
            interfaces = {row.id: row for row in db.query(Interface).filter_by(project_id=project_id).all()}
            executed_case_ids.update(equivalent_case_ids(scenario.steps, cases, interfaces))

    # 2. 运行独立用例 (case_ids)
    for case_id in suite.case_ids or []:
        if case_id in executed_case_ids:
            continue  # 已在场景中执行过，跳过

        case = case_repo.db_get(db, case_id, project_id)
        if not case:
            results.append({
                "type": "case",
                "id": case_id,
                "name": None,
                "passed": False,
                "error": "用例不存在",
            })
            continue

        # run_case 会写报告
        case_name = case.name
        try:
            case_result = execution.run_case(db, case_id, env_id, project_id)
        except Exception as exc:
            db.rollback()
            results.append({"type": "case", "id": case_id, "name": case_name,
                            "passed": False, "error": f"执行异常（{type(exc).__name__}）"})
            executed_case_ids.add(case_id)
            continue

        if isinstance(case_result, dict) and "error" in case_result:
            passed = False
        elif isinstance(case_result, list):  # 数据驱动，返回多条结果
            passed = all(r["passed"] for r in case_result)
        else:
            passed = case_result.get("passed", False)

        results.append({
            "type": "case",
            "id": case_id,
            "name": case_name,
            "passed": passed,
            "detail": case_result,
        })

        executed_case_ids.add(case_id)

    # 3. 汇总统计
    duration_ms = round((perf_counter() - started) * 1000)
    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    failed_count = total - passed_count
    pass_rate = round(passed_count / total * 100, 2) if total > 0 else 0.0

    scenario_count = sum(1 for r in results if r["type"] == "scenario")
    case_count = sum(1 for r in results if r["type"] == "case")

    summary = {
        "suite_id": suite.id,
        "suite_name": suite.name,
        "suite_type": suite.type,
        "started_at": started_at.isoformat(),
        "duration_ms": duration_ms,
        "total": total,
        "passed": passed_count,
        "failed": failed_count,
        "pass_rate": pass_rate,
        "scenario_count": scenario_count,
        "case_count": case_count,
        "results": results,
    }

    # 套件跑完落一张汇总报告("总成绩单"):整体通过 = 全部子项通过
    suite_passed = failed_count == 0 and total > 0
    report_repo.db_create_suite_report(
        db,
        suite_id=suite.id,
        suite_name=suite.name,
        passed=suite_passed,
        detail=summary,
        project_id=project_id,
    )

    return summary
