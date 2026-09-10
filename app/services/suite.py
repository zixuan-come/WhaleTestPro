from datetime import datetime
from time import perf_counter
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.repositories import suite as suite_repo
from app.repositories import case as case_repo
from app.repositories import scenario as scenario_repo
from app.repositories import report as report_repo
from app.services import execution
from app.schemas.suite import SuiteCreate, SuiteUpdate


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
    success = suite_repo.db_delete(db, suite_id, project_id)
    if not success:
        raise HTTPException(status_code=404, detail="测试套件不存在")
    return {"message": "删除成功"}


def run_suite(db: Session, suite_id: int, project_id: int, env_id: int | None = None):
    """
    运行测试套件

    执行流程:
    1. 运行 scenario_ids 中的场景 (链式传参)
    2. 运行 case_ids 中的独立用例
    3. 按 tags 筛选用例并运行 (去重)
    4. 汇总结果并写入报告
    """
    suite = suite_repo.db_get(db, suite_id, project_id)
    if not suite:
        raise HTTPException(status_code=404, detail="测试套件不存在")

    started_at = datetime.utcnow()
    started = perf_counter()

    results = []
    executed_case_ids = set()  # 去重：避免 case_ids 和 tags 重复执行同一用例

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

        # run_chain 会写场景报告
        chain_results = execution.run_chain(
            db,
            scenario.case_ids,
            env_id,
            project_id,
            scenario_id=scenario.id,
            scenario_name=scenario.name,
        )

        passed = all(r["passed"] for r in chain_results)
        results.append({
            "type": "scenario",
            "id": scenario.id,
            "name": scenario.name,
            "passed": passed,
            "steps": len(chain_results),
            "detail": chain_results,
        })

        # 记录已执行的用例（场景中的步骤）
        executed_case_ids.update(scenario.case_ids or [])

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
        case_result = execution.run_case(db, case_id, env_id, project_id)

        if isinstance(case_result, dict) and "error" in case_result:
            passed = False
        elif isinstance(case_result, list):  # 数据驱动，返回多条结果
            passed = all(r["passed"] for r in case_result)
        else:
            passed = case_result.get("passed", False)

        results.append({
            "type": "case",
            "id": case_id,
            "name": case.name,
            "passed": passed,
            "detail": case_result,
        })

        executed_case_ids.add(case_id)

    # 3. 按 tags 筛选用例并运行
    if suite.tags:
        # 与 execution.run_regression 一致:db_list 拉本项目用例后在内存里按 tag 过滤
        # (case_repo 无 db_list_by_tags;用例量级小,内存过滤足够且避免 JSON 列查询的方言差异)
        all_cases = case_repo.db_list(db, project_id)
        tag_set = set(suite.tags)
        tagged_cases = [c for c in all_cases if c.tags and tag_set & set(c.tags)]
        for case in tagged_cases:
            if case.id in executed_case_ids:
                continue  # 去重

            case_result = execution.run_case(db, case.id, env_id, project_id)

            if isinstance(case_result, dict) and "error" in case_result:
                passed = False
            elif isinstance(case_result, list):
                passed = all(r["passed"] for r in case_result)
            else:
                passed = case_result.get("passed", False)

            results.append({
                "type": "case",
                "id": case.id,
                "name": case.name,
                "passed": passed,
                "tags": case.tags,
                "detail": case_result,
            })

            executed_case_ids.add(case.id)

    # 4. 汇总统计
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
