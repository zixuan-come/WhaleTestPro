from app.repositories import case as case_repo
from app.repositories import interface as interface_repo
from app.repositories import report as report_repo
from app.repositories import environment as env_repo
from app.repositories import scenario_report as scenario_report_repo
from app.core.variables import render, extract_match, render_deep
from app.core.assertions import run_assertions
from app.core.sql_runner import run_sql
from app.core.notifier import send_feishu
from app.core.config import settings
from app.core.metrics import regression_pass_rate, regression_coverage
from app.core.circuit_breaker import get_breaker, CircuitBreakerOpen
from app.core.redaction import MASK, is_sensitive_source, sensitive_strings, mask_sensitive as _mask_sensitive
import json
import requests
from datetime import datetime
from time import perf_counter


MAX_RESPONSE_BODY_BYTES = 64 * 1024
MAX_REDACTION_PARSE_BYTES = 256 * 1024


def _response_detail(response):
    content = response.content or b""
    truncated = len(content) > MAX_RESPONSE_BODY_BYTES
    if not content or len(content) > MAX_REDACTION_PARSE_BYTES:
        # Do not parse/copy unbounded JSON just to produce a small report sample.
        body = None
    else:
        try:
            body = _mask_sensitive(response.json())
            if truncated:
                # Truncate only the redacted representation, never raw bytes.
                safe_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
                body = safe_bytes[:MAX_RESPONSE_BODY_BYTES].decode("utf-8", errors="ignore")
        except ValueError:
            body = None if truncated else response.text

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
        raise ValueError(f"环境 id={env_id} 不存在或不属于当前项目")
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



def run_interface(db, interface_id, env_id, project_id):
    """直接执行接口定义，不创建测试用例或测试报告。"""
    interface = interface_repo.db_get(db, interface_id, project_id)
    if interface is None:
        return None
    context = _env_context(db, env_id, project_id)
    request_detail = None
    response_detail = None
    started = perf_counter()
    try:
        rendered_url = _full_url(interface.url, context)
        rendered_headers = render_deep(interface.headers, context)
        rendered_params = render_deep(interface.params, context)
        rendered_body = render_deep(interface.body, context)
        request_detail = {"method": interface.method, "url": rendered_url, "headers": _mask_sensitive(rendered_headers), "params": _mask_sensitive(rendered_params), "body": _mask_sensitive(rendered_body)}
        response = _request(interface, url=rendered_url, headers=rendered_headers, params=rendered_params, json=rendered_body)
        response_detail = _response_detail(response)
        return {"interface_id": interface.id, "interface_name": interface.name, "passed": response.ok, "request": request_detail, "response": response_detail, "duration_ms": round((perf_counter() - started) * 1000)}
    except Exception as exc:
        return {"interface_id": interface.id, "interface_name": interface.name, "passed": False, "request": request_detail, "response": response_detail, "error": str(exc), "duration_ms": round((perf_counter() - started) * 1000)}
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
    report_secrets = set(sensitive_strings(context))
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
                    match = extract_match(data, path)
                    extracted = match.value
                    sensitive = is_sensitive_source(str(match.full_path)) or is_sensitive_source(var_name)
                    report_secrets.update(sensitive_strings(extracted, sensitive=sensitive))
                    context[var_name] = extracted
                    extracted_variables[var_name] = MASK if sensitive else extracted
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

    # Keep raw values only in the in-memory execution context. Aliases and
    # templated request/response evidence must not erase their sensitive origin.
    report_secrets = tuple(sorted(report_secrets, key=len, reverse=True))
    # Redact evidence, not operational IDs/statuses/timing that may coincidentally
    # equal a small numeric secret. Persistence still requires real case IDs.
    for record in report_steps + results:
        for field in ("case_name", "extracted_variables", "error"):
            if field in record:
                record[field] = _mask_sensitive(record[field], secrets=report_secrets)
        if isinstance(record.get("case_name"), str):
            # Replacement can expand a valid name beyond String(100).
            record["case_name"] = record["case_name"][:100]
        assertions = record.get("assertions")
        if assertions:
            # Only this internally generated first row is status metadata;
            # user-defined assertions still have their evidence redacted.
            metadata_count = 1 if "sequence" in record else 0
            record["assertions"] = assertions[:metadata_count] + [
                {**assertion,
                 "expected": _mask_sensitive(assertion.get("expected"), secrets=report_secrets),
                 "actual": _mask_sensitive(assertion.get("actual"), secrets=report_secrets)}
                for assertion in assertions[metadata_count:]
            ]
        for detail_key, fields in (
            ("request_detail", ("url", "headers", "params", "body")),
            ("response_detail", ("headers", "body")),
        ):
            detail = record.get(detail_key)
            if detail is not None:
                for field in fields:
                    if field in detail:
                        detail[field] = _mask_sensitive(detail[field], secrets=report_secrets)
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
        kwargs.setdefault("timeout", settings.REQUEST_TIMEOUT_SECONDS)
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
    result = None
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
        result = {
            "passed": passed,
            "expected_status": case.expected_status,
            "actual_status": response.status_code,
            "assertions": assertions_results,
        }
    except Exception as e:
        result = {"passed": False, "error": str(e)}
    finally:
        try:
            run_sql(db, render_deep(case.teardown_sql, context))
        except Exception as exc:
            # Cleanup failure must remain a failed test result, not escape and
            # prevent report persistence or replace the original error.
            result = result or {"passed": False}
            result["passed"] = False
            result["teardown_error"] = str(exc)
    return result


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
        "passed": total > 0 and passed_count == total,
        "execution_status": "completed" if total else "no_tests",
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

