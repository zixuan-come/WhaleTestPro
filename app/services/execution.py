from app.repositories import case as case_repo
from app.repositories import interface as interface_repo
from app.repositories import report as report_repo
from app.repositories import environment as env_repo
from app.core.variables import render, extract, render_deep
from app.core.assertions import run_assertions
from app.core.sql_runner import run_sql
from app.core.notifier import send_feishu
from app.core.config import settings
from app.core.metrics import regression_pass_rate, regression_coverage
from app.core.circuit_breaker import get_breaker, CircuitBreakerOpen
import requests


def _env_context(db, env_id):
    if env_id is None:
        return {}
    env = env_repo.db_get(db, env_id)
    if env is None:
        return {}
    return {**(env.variables or {}), "base_url": env.base_url}


def run_case(db, case_id, env_id=None):
    case = case_repo.db_get(db, case_id)
    if case is None:
        return {"error": "用例不存在"}

    interface = interface_repo.db_get(db, case.interface_id)
    if interface is None:
        return {"error": "用例关联的接口不存在"}

    base_ctx = _env_context(db, env_id)
    if case.datasets:
        result = [_run_with_retry(db, case, interface, {**base_ctx, **row}) for row in case.datasets]
        passed = all(r["passed"] for r in result)
    else:
        result = _run_with_retry(db, case, interface, base_ctx)
        passed = result["passed"]

    report_repo.db_create(db, case_id=case_id, passed=passed, detail=result)
    return result


def run_chain(db, case_ids, env_id=None):
    context = _env_context(db, env_id)
    results = []
    for case_id in case_ids:
        case = case_repo.db_get(db, case_id)
        if case is None:
            results.append({"case_id": case_id, "error": "用例不存在"})
            continue

        interface = interface_repo.db_get(db, case.interface_id)
        if interface is None:
            results.append({"case_id": case_id, "error": "接口不存在"})
            continue

        try:
            response = _request(
                interface,
                url=render_deep(interface.url, context),
                headers=render_deep(interface.headers, context),
                params=render_deep(interface.params, context),
                json=render_deep(interface.body, context),
            )
        except Exception as e:
            results.append({"case_id": case_id, "passed": False, "error": str(e)})
            continue

        status_passed = response.status_code == case.expected_status
        assertions_results = run_assertions(response, case.assertions, db)
        passed = status_passed and all(r["passed"] for r in assertions_results)

        if case.extract_rules:
            data = response.json()
            for var_name, path in case.extract_rules.items():
                context[var_name] = extract(data, path)

        results.append({
            "case_id": case_id,
            "passed": passed,
            "expected_status": case.expected_status,
            "actual_status": response.status_code,
            "assertions": assertions_results,
        })

    return results


def _request(interface, **kwargs):
    breaker = get_breaker(interface.id)
    if not breaker.allow_request():
        raise CircuitBreakerOpen(f"接口 {interface.id} 熔断打开，快速失败")
    try:
        response = requests.request(method=interface.method, **kwargs)
    except Exception:
        breaker.record_failure()      # 连不上/超时 = 下游不可用
        raise
    if response.status_code >= 500:
        breaker.record_failure()      # 5xx = 下游崩了
    else:
        breaker.record_success()      # 2xx/3xx/4xx = 下游活着(决策 A:4xx 不算挂)
    return response



def _run_once(db, case, interface, context):
    try:
        run_sql(db, render_deep(case.setup_sql, context))
        response = _request(
            interface,
            url=render_deep(interface.url, context),
            headers=render_deep(interface.headers, context),
            params=render_deep(interface.params, context),
            json=render_deep(interface.body, context),
        )
        status_passed = response.status_code == case.expected_status
        assertions_results = run_assertions(response, render_deep(case.assertions, context), db)
        passed = status_passed and all(r["passed"] for r in assertions_results)
        return {
            "passed": passed,
            "expected_status": case.expected_status,
            "actual_status": response.status_code,
            "assertions": assertions_results,
        }
    except Exception as e:
        return {"passed": False, "error": str(e)}
    finally:
        run_sql(db, render_deep(case.teardown_sql, context))


def _run_with_retry(db, case, interface, context):
    attempts = (case.retries or 0) + 1
    for i in range(attempts):
        result = _run_once(db, case, interface, context)
        if result["passed"]:
            break
    result["attempts"] = i + 1
    return result


def _result_passed(result):
    if isinstance(result, list):
        return all(r["passed"] for r in result)
    return result.get("passed", False)


def run_regression(db, case_ids=None, env_id=None, tag=None, notify=False):
    if case_ids is None:
        cases = case_repo.db_list(db)
        if tag is not None:
            cases = [c for c in cases if c.tags and tag in c.tags]
        case_ids = [c.id for c in cases]
    results = []
    for case_id in case_ids:
        try:
            result = run_case(db, case_id, env_id)
            results.append({"case_id": case_id, "passed": _result_passed(result), "result": result})
        except Exception as e:
            results.append({"case_id": case_id, "passed": False, "error": str(e)})
    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])

    pass_rate = passed_count / total if total else 0

    all_interfaces = interface_repo.db_list(db)
    covered_ids = {c.interface_id for c in case_repo.db_list(db)}
    interface_total = len(all_interfaces)
    interface_covered = len(covered_ids)
    coverage = interface_covered / interface_total if interface_total else 0

    regression_pass_rate.set(pass_rate)
    regression_coverage.set(coverage)
    summary = {
        "passed": passed_count == total,
        "total": total,
        "passed_count": passed_count,
        "failed_count": total - passed_count,
        "results": results,
        "pass_rate": pass_rate,
        "interface_total": interface_total,
        "interface_covered": interface_covered,
        "interface_coverage": coverage,
    }
    if notify and settings.FEISHU_WEBHOOK:
        content = f"回归结果: {summary['passed_count']}/{summary['total']} 通过, 通过率 {pass_rate:.0%}, 接口覆盖率 {coverage:.0%}"
        send_feishu(settings.FEISHU_WEBHOOK, content)
    return summary






