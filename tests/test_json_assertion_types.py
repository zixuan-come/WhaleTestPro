"""Typed JSON checks must agree in functional tests and Locust iterations."""
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.core.assertions import run_assertions
from app.core.perf_plan import check_assertions, execute_iteration
from app.schemas.perf_plan import PerfLoadConfig


CASES = [
    ("json_eq", 1, True, False),
    ("json_eq", True, 1, False),
    ("json_eq", 0, False, False),
    ("json_eq", False, 0, False),
    ("json_eq", {"items": [{"flag": 1}]}, {"items": [{"flag": True}]}, False),
    ("json_eq", {"items": [{"flag": True}]}, {"items": [{"flag": 1}]}, False),
    ("json_eq", True, True, True),
    ("json_eq", False, False, True),
    ("json_eq", 1, 1.0, True),
    ("json_eq", {"items": [1, {"value": 2.0}]}, {"items": [1.0, {"value": 2}]}, True),
    ("json_eq", {"a": 1, "b": False}, {"b": False, "a": 1.0}, True),
    ("json_eq", "1", 1, False),
    ("json_eq", [], {}, False),
    ("json_eq", [1, 2], [2, 1], False),
    ("json_eq", None, None, True),
    ("json_eq", None, False, False),
    ("json_contains", [1], True, False),
    ("json_contains", [True], 1, False),
    ("json_contains", [0], False, False),
    ("json_contains", [False], 0, False),
    ("json_contains", [{"flag": 1}], {"flag": True}, False),
    ("json_contains", [{"flag": True}], {"flag": 1}, False),
    ("json_contains", [False, True], True, True),
    ("json_contains", [1, 2], 1.0, True),
    ("json_contains", [{"items": [1.0, None]}], {"items": [1, None]}, True),
    ("json_contains", "订单查询成功", "查询", True),
    ("json_contains", "订单查询成功", "失败", False),
    ("json_contains", {"flag": False}, "flag", True),
    ("json_contains", {"flag": False}, "missing", False),
]


@pytest.mark.parametrize("kind,actual,expected,passed", CASES)
def test_functional_and_load_assertions_share_json_types(kind, actual, expected, passed):
    response = SimpleNamespace(json=lambda: {"value": actual})
    rule = {"type": kind, "path": "$.value", "expected": expected}
    result = run_assertions(response, [rule], None)[0]
    assert result["passed"] is passed
    if passed:
        check_assertions(response, [SimpleNamespace(**rule)], {})
    else:
        with pytest.raises(ValueError, match="业务断言失败"):
            check_assertions(response, [SimpleNamespace(**rule)], {})


@pytest.mark.parametrize("actual,expected", [(None, "x"), (1, 1), ({"a": 1}, ["a"])])
def test_invalid_contains_operands_still_fail(actual, expected):
    response = SimpleNamespace(json=lambda: {"value": actual})
    rule = {"type": "json_contains", "path": "$.value", "expected": expected}
    assert run_assertions(response, [rule], None)[0]["passed"] is False
    with pytest.raises(TypeError):
        check_assertions(response, [SimpleNamespace(**rule)], {})


@pytest.mark.parametrize("kind,actual,expected", [
    ("json_eq", {"flag": 1}, {"flag": True}),
    ("json_contains", [{"flag": False}], {"flag": 0}),
])
def test_load_iteration_records_business_failure_for_json_type_mismatch(kind, actual, expected):
    class Response:
        status_code = 200
        headers = {}
        elapsed = timedelta(0)
        verdict = None
        def json(self): return {"value": actual}
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def success(self): self.verdict = True
        def failure(self, message): self.verdict = message
    response = Response()
    client = SimpleNamespace(cookies={}, request=lambda *a, **kw: response)
    plan = PerfLoadConfig(steps=[{"path": "/orders", "assertions": [
        {"type": kind, "path": "$.value", "expected": expected}]}])
    result = execute_iteration(client, "http://synthetic.invalid", plan, "review-user", 1)
    assert result["passed"] is False and response.verdict == "步骤状态码、业务断言或变量提取失败"
