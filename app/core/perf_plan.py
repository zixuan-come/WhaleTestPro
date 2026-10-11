"""Execute one isolated HTTP iteration using Locust's instrumented client."""
from copy import deepcopy
import re
from time import perf_counter

from jsonschema import validate
from app.core.variables import extract
from app.schemas.perf_plan import PerfLoadConfig, validate_path


def render_value(value, context):
    if isinstance(value, str):
        full = re.fullmatch(r"\$\{(\w+)\}", value)
        if full:
            return deepcopy(context[full.group(1)])
        return re.sub(r"\$\{(\w+)\}", lambda match: str(context[match.group(1)]), value)
    if isinstance(value, dict):
        return {key: render_value(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [render_value(item, context) for item in value]
    return value


def check_assertions(response, assertions, context):
    for assertion in assertions:
        expected = render_value(assertion.expected, context)
        kind = assertion.type
        if kind == "json_schema":
            validate(response.json(), expected)
            continue
        if kind.startswith("json_"):
            actual = extract(response.json(), assertion.path)
        elif kind.startswith("header_"):
            actual = response.headers.get(assertion.path)
        else:
            actual = response.elapsed.total_seconds() * 1000
        passed = {"json_eq": lambda: actual == expected,
                  "header_eq": lambda: actual == expected,
                  "json_contains": lambda: expected in actual,
                  "header_contains": lambda: expected in actual,
                  "json_gt": lambda: actual > expected,
                  "json_lt": lambda: actual < expected,
                  "response_time_lt": lambda: actual < expected}[kind]()
        if not passed:
            raise ValueError("业务断言失败")


def execute_iteration(client, host: str, plan: PerfLoadConfig, vu_id: str, iteration: int):
    started = perf_counter()
    context = deepcopy(plan.variables)
    if plan.datasets:
        context.update(deepcopy(plan.datasets[(iteration - 1) % len(plan.datasets)]))
    context.update({"_vu_id": vu_id, "_iteration": iteration})
    # Cookies and extracted state must never leak into the next iteration.
    client.cookies.clear()
    passed = True
    for index, step in enumerate(plan.steps):
        failed = False
        # Names never interpolate variables or query parameters into statistics.
        stat_name = f"step_{index + 1:02d}"
        try:
            path = validate_path(str(render_value(step.path, context)))
            headers = {key: str(render_value(value, context)) for key, value in step.headers.items()}
            if any("\r" in item or "\n" in item for item in headers.values()):
                raise ValueError("请求头渲染后无效")
            kwargs = dict(headers=headers, params=render_value(step.params, context),
                          timeout=plan.timeout_seconds, allow_redirects=step.allow_redirects,
                          catch_response=True, name=stat_name)
            if step.body_type == "json":
                body = render_value(step.body, context)
                if body is None:
                    kwargs["data"] = b"null"
                    if not any(key.lower() == "content-type" for key in headers):
                        headers["Content-Type"] = "application/json"
                else:
                    kwargs["json"] = body
            elif step.body_type == "form":
                kwargs["data"] = render_value(step.body, context)
            elif step.body_type == "raw":
                # Explicit bytes give Requests the correct UTF-8 Content-Length.
                kwargs["data"] = str(render_value(step.body, context)).encode("utf-8")
            with client.request(step.method, host.rstrip("/") + path, **kwargs) as response:
                try:
                    if step.expected_status is not None:
                        if response.status_code != step.expected_status:
                            raise ValueError("状态码不符合预期")
                    elif not 200 <= response.status_code < 400:
                        raise ValueError("HTTP 请求失败")
                    check_assertions(response, step.assertions, context)
                    # Extract into a temporary map: a partial extraction is not success.
                    extracted = {name: extract(response.json(), rule)
                                 for name, rule in step.extract_rules.items()}
                    context.update(extracted)
                    response.success()
                except Exception:
                    failed = True
                    # Never log response content, exception URLs or credentials.
                    response.failure("步骤状态码、业务断言或变量提取失败")
        except Exception:
            failed = True
            # Validation before send has no HTTP sample, but must count as failure.
            client.request_event.fire(request_type=step.method, name=stat_name,
                                      response_time=0, response_length=0,
                                      exception=RuntimeError("请求准备或发送失败"), context={})
        if failed:
            passed = False
            if plan.stop_on_failure:
                break
    return {"passed": passed, "duration_ms": (perf_counter() - started) * 1000}
