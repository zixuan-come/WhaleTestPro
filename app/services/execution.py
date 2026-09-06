from app.repositories import case as case_repo
from app.repositories import interface as interface_repo
from app.repositories import report as report_repo
from app.repositories import environment as env_repo
from app.repositories import scenario_report as scenario_report_repo
from app.core.variables import render, extract, render_deep
from app.core.assertions import run_assertions
from app.core.sql_runner import run_sql
from app.core.notifier import send_feishu
from app.core.config import settings
from app.core.metrics import regression_pass_rate, regression_coverage
from app.core.circuit_breaker import get_breaker, CircuitBreakerOpen
import requests
from datetime import datetime
from time import perf_counter


SENSITIVE_KEYS = {
    "password", "passwd", "pwd", "token", "authorization", "cookie",
    "set-cookie", "secret", "api-key", "x-api-key", "phone", "mobile",
    "id_card", "idcard",
}
MAX_RESPONSE_BODY_BYTES = 64 * 1024


def _is_sensitive_key(key):
    normalized = str(key).lower().replace("_", "-")
    return (
        normalized in SENSITIVE_KEYS
        or normalized.endswith("-token")
        or normalized.endswith("-password")
        or normalized.endswith("-secret")
    )


def _mask_sensitive(value):
    if isinstance(value, dict):
        return {
            key: "***" if _is_sensitive_key(key) else _mask_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_mask_sensitive(item) for item in value]
    return value


def _response_detail(response):
    content = response.content or b""
    truncated = len(content) > MAX_RESPONSE_BODY_BYTES
    if not content:
        body = None
    elif truncated:
        body = content[:MAX_RESPONSE_BODY_BYTES].decode(response.encoding or "utf-8", errors="replace")
    else:
        try:
            body = response.json()
        except ValueError:
            body = response.text

    return {
        "status_code": response.status_code,
        "headers": _mask_sensitive(dict(response.headers)),
        "body": _mask_sensitive(body),
        "body_truncated": truncated,
    }


def _env_context(db, env_id, project_id):
    if env_id is None:
        return {}
    env = env_repo.db_get(db, env_id, project_id)
    if env is None:
        return {}
    return {**(env.variables or {}), "base_url": env.base_url}


def _full_url(interface_url, context):
    path = render_deep(interface_url, context)
    base = context.get("base_url", "")
    return base.rstrip("/") + "/" + path.lstrip("/")


def run_case(db, case_id, env_id, project_id):
    case = case_repo.db_get(db, case_id, project_id)
    if case is None:
        return {"error": "用例不存在"}

    interface = interface_repo.db_get(db, case.interface_id, project_id)
    if interface is None:
        return {"error": "用例关联的接口不存在"}

    base_ctx = _env_context(db, env_id, project_id)
    if case.datasets:
        result = [_run_with_retry(db, case, interface, {**base_ctx, **row}) for row in case.datasets]
        passed = all(r["passed"] for r in result)
    else:
        result = _run_with_retry(db, case, interface, base_ctx)
        passed = result["passed"]

    report_repo.db_create(db, case_id=case_id, passed=passed, detail=result, project_id=project_id)
    return result


def run_chain(
    db,
    case_ids,
    env_id,
    project_id,
    scenario_id=None,
    scenario_name=None,
):
    report_started_at = datetime.utcnow()
    report_started = perf_counter()
    context = _env_context(db, env_id, project_id)
    results = []
    report_steps = []
    for sequence, case_id in enumerate(case_ids, start=1):
        step_started = perf_counter()
        case = case_repo.db_get(db, case_id, project_id)
        if case is None:
            result = {"case_id": case_id, "case_name": None, "passed": False, "error": "用例不存在"}
            results.append(result)
            report_steps.append({
                "sequence": sequence,
                "case_id": case_id,
                "case_name": None,
                "passed": False,
                "request_detail": None,
                "response_detail": None,
                "assertions": None,
                "extracted_variables": None,
                "error": result["error"],
                "duration_ms": round((perf_counter() - step_started) * 1000),
            })
            continue

        interface = interface_repo.db_get(db, case.interface_id, project_id)
        if interface is None:
            result = {"case_id": case_id, "case_name": case.name, "passed": False, "error": "接口不存在"}
            results.append(result)
            report_steps.append({
                "sequence": sequence,
                "case_id": case_id,
                "case_name": case.name,
                "passed": False,
                "request_detail": None,
                "response_detail": None,
                "assertions": None,
                "extracted_variables": None,
                "error": result["error"],
                "duration_ms": round((perf_counter() - step_started) * 1000),
            })
            continue

        request_detail = None
        response_detail = None
        assertions_results = []
        extracted_variables = {}
        error = None
        actual_status = None
        try:
            rendered_url = _full_url(interface.url, context)
            rendered_headers = render_deep(interface.headers, context)
            rendered_params = render_deep(interface.params, context)
            rendered_body = render_deep(interface.body, context)
            request_detail = {
                "method": interface.method,
                "url": rendered_url,
                "headers": _mask_sensitive(rendered_headers),
                "params": _mask_sensitive(rendered_params),
                "body": _mask_sensitive(rendered_body),
            }
            response = _request(
                interface,
                url=rendered_url,
                headers=rendered_headers,
                params=rendered_params,
                json=rendered_body,
            )
            actual_status = response.status_code
            response_detail = _response_detail(response)
            status_passed = response.status_code == case.expected_status
            rendered_assertions = render_deep(case.assertions, context)
            assertions_results = run_assertions(response, rendered_assertions, db)
            passed = status_passed and all(item["passed"] for item in assertions_results)

            if case.extract_rules:
                data = response.json()
                rendered_extract_rules = render_deep(case.extract_rules, context)
                for var_name, path in rendered_extract_rules.items():
                    extracted = extract(data, path)
                    context[var_name] = extracted
                    extracted_variables[var_name] = extracted
        except Exception as e:
            passed = False
            error = str(e)

        result = {
            "case_id": case_id,
            "case_name": case.name,
            "passed": passed,
            "expected_status": case.expected_status,
            "actual_status": actual_status,
            "assertions": assertions_results,
        }
        if error:
            result["error"] = error
        results.append(result)
        report_assertions = []
        if actual_status is not None:
            report_assertions.append({
                "type": "status_code",
                "passed": actual_status == case.expected_status,
                "expected": case.expected_status,
                "actual": actual_status,
            })
        report_assertions.extend(assertions_results)
        report_steps.append({
            "sequence": sequence,
            "case_id": case_id,
            "case_name": case.name,
            "passed": passed,
            "request_detail": request_detail,
            "response_detail": response_detail,
            "assertions": report_assertions or None,
            "extracted_variables": _mask_sensitive(extracted_variables) or None,
            "error": error,
            "duration_ms": round((perf_counter() - step_started) * 1000),
        })

    if scenario_id is None:
        for result, step in zip(results, report_steps):
            report_repo.db_create(
                db,
                case_id=result["case_id"],
                passed=result["passed"],
                detail={"chain": True, "step": step},
                project_id=project_id,
            )

    if scenario_id is not None and scenario_name is not None:
        scenario_report_repo.db_create(
            db,
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            project_id=project_id,
            created_at=report_started_at,
            duration_ms=round((perf_counter() - report_started) * 1000),
            steps=report_steps,
        )

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
            url=_full_url(interface.url, context),
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


def run_regression(db, case_ids=None, env_id=None, tag=None, notify=False, project_id=None):
    if case_ids is None:
        cases = case_repo.db_list(db, project_id)
        if tag is not None:
            cases = [c for c in cases if c.tags and tag in c.tags]
        case_ids = [c.id for c in cases]
    else:
        selected_case_ids = set(case_ids)
        cases = [c for c in case_repo.db_list(db, project_id) if c.id in selected_case_ids]
    results = []
    for case_id in case_ids:
        try:
            result = run_case(db, case_id, env_id, project_id)
            results.append({"case_id": case_id, "passed": _result_passed(result), "result": result})
        except Exception as e:
            results.append({"case_id": case_id, "passed": False, "error": str(e)})
    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])

    pass_rate = passed_count / total if total else 0

    all_interfaces = interface_repo.db_list(db, project_id)
    interface_ids = {interface.id for interface in all_interfaces}
    covered_ids = {case.interface_id for case in cases if case.interface_id in interface_ids}
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

