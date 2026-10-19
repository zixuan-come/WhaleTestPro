"""Explicit regression selection, read-only preview and existing suite execution."""
import hashlib
import json
from urllib.parse import urlsplit

from fastapi import HTTPException

from app.core.metrics import regression_pass_rate, regression_coverage
from app.services.project_notification import notify_regression
from app.models.case import Case
from app.models.environment import Environment
from app.models.interface import Interface
from app.models.scenario import Scenario
from app.models.suite import TestSuite
from app.services import execution, suite
from app.services.execution_tracking import tracked
from app.core.scenario_steps import equivalent_case_ids


def _assets(db, model, project_id):
    return {row.id: row for row in db.query(model).filter(model.project_id == project_id).order_by(model.id).all()}


def options(db, project_id):
    interfaces = _assets(db, Interface, project_id)
    return {
        "suites": [{"id": row.id, "name": row.name, "description": row.description}
                   for row in _assets(db, TestSuite, project_id).values()],
        "cases": [{"id": row.id, "name": row.name,
                   "interface_name": interfaces[row.interface_id].name if row.interface_id in interfaces else "接口已删除"}
                  for row in _assets(db, Case, project_id).values()],
    }


def preview(db, project_id, selection):
    cases, scenarios = _assets(db, Case, project_id), _assets(db, Scenario, project_id)
    suites, interfaces = _assets(db, TestSuite, project_id), _assets(db, Interface, project_id)
    selected = suites if selection.mode == "suite" else cases
    if any(number not in selected for number in selection.ids):
        raise HTTPException(404, "部分测试内容不存在或不属于当前项目，请重新选择")
    env = db.query(Environment).filter_by(id=selection.env_id, project_id=project_id).first() if selection.env_id else None
    if selection.env_id and env is None:
        raise HTTPException(404, "所选环境不存在或不属于当前项目")
    warnings, referenced = [], {}

    def remember(row):
        referenced[(row.__tablename__, row.id)] = {column.name: getattr(row, column.name) for column in row.__table__.columns}

    if env:
        remember(env)

    def case_item(number):
        row = cases.get(number)
        if row is None:
            warnings.append(f"用例 #{number} 已删除，请更新测试内容")
            return {"type": "case", "id": number, "name": f"用例 #{number}（已删除）"}
        remember(row)
        interface = interfaces.get(row.interface_id)
        if interface is None:
            warnings.append(f"用例「{row.name}」关联的接口已删除")
        else:
            remember(interface)
            if not env and urlsplit(interface.url).scheme not in {"http", "https"}:
                warnings.append("存在使用相对地址的用例，请选择测试环境")
        return {"type": "case", "id": row.id, "name": row.name}

    groups, case_count, scenario_count, step_count = [], 0, 0, 0
    if selection.mode == "case":
        groups = [case_item(number) for number in selection.ids]
        case_count = len(groups)
    else:
        for number in selection.ids:
            current, items, used = suites[number], [], set()
            remember(current)
            for scenario_id in current.scenario_ids or []:
                scenario = scenarios.get(scenario_id)
                if scenario is None:
                    warnings.append(f"套件「{current.name}」中的场景 #{scenario_id} 已删除")
                    items.append({"type": "scenario", "id": scenario_id, "name": f"场景 #{scenario_id}（已删除）", "steps": []})
                else:
                    remember(scenario)
                    if getattr(scenario, 'steps', None) is None:
                        steps = [case_item(case_id) for case_id in scenario.case_ids or []]
                        used.update(scenario.case_ids or [])
                    else:
                        steps = []
                        for step in scenario.steps:
                            if step.get('missing_reason'):
                                warnings.append(f"场景「{scenario.name}」中的步骤「{step['name']}」关联接口已失效")
                            else:
                                if not env:
                                    warnings.append('存在使用相对地址的步骤，请选择测试环境')
                            steps.append({'type': 'case', 'id': step.get('source_case_id'), 'step_id': step['step_id'],
                                          'name': step['name'], 'interface_id': step.get('interface_id')})
                        used.update(equivalent_case_ids(scenario.steps, cases, interfaces))
                    if not steps:
                        warnings.append(f"场景「{scenario.name}」没有执行步骤")
                    items.append({"type": "scenario", "id": scenario.id, "name": scenario.name, "steps": steps})
                    step_count += len(steps)
                scenario_count += 1
            explicit = list(current.case_ids or [])
            for case_id in explicit:
                if case_id not in used:
                    items.append(case_item(case_id))
                    used.add(case_id)
                    case_count += 1
            if not items:
                warnings.append(f"套件「{current.name}」没有可执行内容")
            groups.append({"type": "suite", "id": current.id, "name": current.name, "items": items})
    # Snapshot the selection and all reachable configuration. No request secrets
    # leave the server; only the digest is returned for the start-time recheck.
    source = {"project_id": project_id, "selection": selection.model_dump(include={"mode", "ids", "env_id"}),
              "resources": [referenced[key] for key in sorted(referenced)]}
    key = hashlib.sha256(json.dumps(source, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    warnings = list(dict.fromkeys(warnings))
    return {"mode": selection.mode, "groups": groups, "suite_count": len(groups) if selection.mode == "suite" else 0,
            "scenario_count": scenario_count, "case_count": case_count, "step_count": step_count,
            "total": scenario_count + case_count, "warnings": warnings, "ready": not warnings,
            "preview_key": key}


def run(db, project_id, selection, *, report_name=None):
    plan = preview(db, project_id, selection)
    if plan["preview_key"] != selection.preview_key:
        raise HTTPException(409, "测试内容或环境已变更，请刷新执行清单后再开始")
    if not plan["ready"]:
        raise HTTPException(400, "；".join(plan["warnings"]))
    title = report_name or ("套件回归" if selection.mode == "suite" else "用例回归")
    return _run_plan(db, plan, selection.env_id, project_id, title, selection.notify)


@tracked("regression", include_report_id=True)
def _run_plan(db, plan, env_id, project_id, report_name, notify=False):
    results, covered = [], set()
    # Copy IDs/names before any child report commit expires ORM objects.
    case_interfaces = {row.id: row.interface_id for row in _assets(db, Case, project_id).values()}
    interface_ids = set(_assets(db, Interface, project_id))
    for group in plan["groups"]:
        try:
            if group["type"] == "suite":
                detail = suite.run_suite(db, group["id"], project_id, env_id)
                passed = detail["total"] > 0 and detail["failed"] == 0
                for item in group["items"]:
                    for case in item.get("steps", [item]):
                        if case.get('interface_id') is not None:
                            covered.add(case['interface_id'])
                        elif case.get("id") in case_interfaces:
                            covered.add(case_interfaces[case["id"]])
            else:
                detail = execution.run_case(db, group["id"], env_id, project_id)
                passed = execution._result_passed(detail)
                covered.add(case_interfaces[group["id"]])
            results.append({"type": group["type"], "id": group["id"], "name": group["name"], "passed": passed, "detail": detail})
        except Exception as exc:
            db.rollback()
            results.append({"type": group["type"], "id": group["id"], "name": group["name"], "passed": False,
                            "error": f"执行异常（{type(exc).__name__}）"})
    total = passed_count = 0
    for item in results:
        if item["type"] == "suite" and item.get("detail", {}).get("total"):
            total += item["detail"]["total"]
            passed_count += item["detail"]["passed"]
        else:
            total += 1
            passed_count += int(item["passed"])
    rate, coverage = passed_count / total if total else 0, len(covered & interface_ids) / len(interface_ids) if interface_ids else 0
    regression_pass_rate.set(rate)
    regression_coverage.set(coverage)
    summary = {"passed": total > 0 and passed_count == total, "total": total, "passed_count": passed_count,
               "failed_count": total - passed_count, "pass_rate": rate, "results": results,
               "interface_total": len(interface_ids), "interface_covered": len(covered & interface_ids), "interface_coverage": coverage}
    if notify:
        notify_regression(db, project_id, summary)
    return summary
