"""Synthetic regression evidence for the 2026-10-11 review; no live services."""
import ast
import asyncio
import base64
import json
import traceback
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.requests import Request
from starlette.responses import Response

from app.core import redaction
from app.core.exception_handlers import unhandled_exception_handler
from app.models.case import Case
from app.models.interface import Interface
from app.models.report import TestReport as Report
from app.schemas.case import CaseCreate, CaseUpdate, CaseOut
from app.schemas.suite import SuiteCreate, SuiteUpdate
from app.schemas.traffic_record import TrafficRecordCreate
from app.services import execution
from app.tasks import traffic
from tests.test_suite_service import db
from tests.test_tail_fixes_recording import consumer


@pytest.mark.parametrize("model", [SuiteCreate, SuiteUpdate])
@pytest.mark.parametrize("field,value", [
    ("case_ids", list(range(101))), ("scenario_ids", list(range(101))),
    ("tags", ["tag"] * 21), ("tags", [" "]),
])
def test_suite_selection_limits_apply_to_create_and_update(model, field, value):
    common = {"name": "review", "type": "case"} if model is SuiteCreate else {}
    with pytest.raises(ValidationError):
        model(**common, **{field: value})


def test_suite_update_preserves_omission_null_and_limit_boundaries():
    assert SuiteUpdate().model_dump(exclude_unset=True) == {}
    assert SuiteUpdate(case_ids=None).model_dump(exclude_unset=True) == {"case_ids": None}
    assert len(SuiteUpdate(case_ids=list(range(100)), tags=["tag"] * 20).case_ids) == 100


@pytest.mark.parametrize("model", [CaseCreate, CaseUpdate])
@pytest.mark.parametrize("datasets", [[1], [None], ["row"], [{} , []]])
def test_case_write_rejects_non_object_dataset_rows(model, datasets):
    with pytest.raises(ValidationError):
        model(name="review", interface_id=1, expected_status=200, datasets=datasets)


@pytest.mark.parametrize("datasets", [[1], [None], [{"valid": 1}, "bad"]])
def test_historical_invalid_dataset_produces_failure_report_without_traffic(db, monkeypatch, datasets):
    interface = Interface(name="dataset", method="GET", url="/unused", project_id=1)
    db.add(interface)
    db.flush()
    case = Case(name="historical", interface_id=interface.id, expected_status=200,
                project_id=1, datasets=datasets)
    db.add(case)
    db.commit()
    # A bad historical row remains inspectable; writes are stricter than reads.
    assert CaseOut.model_validate(case).datasets == datasets
    sent = Mock(side_effect=AssertionError("must validate all rows before sending"))
    monkeypatch.setattr(execution, "_request", sent)
    result = execution.run_case(db, case.id, None, 1)
    assert result["passed"] is False and "数据" in result["error"]
    sent.assert_not_called()
    report = db.query(Report).one()
    assert report.passed is False and report.detail == result
    assert db.get(Case, case.id).datasets == datasets


@pytest.mark.parametrize("header,value,secret", [
    ("Authorization", "Bearer synthetic-header-only-token", "synthetic-header-only-token"),
    ("authorization", "bearer synthetic-header-only-token", "synthetic-header-only-token"),
    ("Authorization", "Basic " + base64.b64encode(b"review:synthetic-basic-password").decode(), "synthetic-basic-password"),
    ("Cookie", "session=synthetic-cookie-secret; theme=dark", "synthetic-cookie-secret"),
    ("Set-Cookie", "session=synthetic-cookie-secret; Path=/; HttpOnly", "synthetic-cookie-secret"),
])
def test_header_credential_components_are_tracked(header, value, secret):
    secrets = set(redaction.sensitive_strings({header: value}))
    safe = redaction.mask_sensitive({header: value, "echo": secret}, secrets=secrets)
    assert safe[header] == safe["echo"] == "***"


@pytest.mark.parametrize("credential", [
    "!not-base64!", base64.b64encode(b"\xff:synthetic-password").decode(),
    base64.b64encode(b"synthetic-no-colon").decode(),
])
def test_malformed_basic_header_stays_masked_without_decode_failure(credential):
    value = "Basic " + credential
    secrets = set(redaction.sensitive_strings({"Authorization": value}))
    safe = redaction.mask_sensitive({"Authorization": value, "echo": credential}, secrets=secrets)
    assert safe == {"Authorization": "***", "echo": "***"}


def test_cookie_parse_failure_still_masks_sensitive_header(monkeypatch):
    def invalid_cookie(_value):
        raise redaction.CookieError("synthetic malformed cookie")
    monkeypatch.setattr(redaction, "SimpleCookie", lambda: SimpleNamespace(load=invalid_cookie))
    value = "synthetic malformed cookie"
    secrets = set(redaction.sensitive_strings({"Cookie": value}))
    safe = redaction.mask_sensitive({"Cookie": value, "echo": value}, secrets=secrets)
    assert safe == {"Cookie": "***", "echo": "***"}


def test_bearer_only_source_is_masked_in_interface_chain_and_case_evidence(db, monkeypatch):
    secret = "synthetic-header-only-token"
    interface = Interface(name="header-only", method="GET", url="/unused", project_id=1,
                          headers={"Authorization": "Bearer " + secret})
    db.add(interface)
    db.flush()
    case = Case(name="header-only", interface_id=interface.id, expected_status=200,
                project_id=1, assertions=[{"type": "json_eq", "path": "$.echo", "expected": secret}])
    db.add(case)
    db.commit()
    sent = []
    def request(*args, **kwargs):
        sent.append(kwargs)
        result = requests.Response()
        result.status_code = 200
        result._content = json.dumps({"echo": secret}).encode()
        return result
    monkeypatch.setattr(execution, "_request", request)
    direct = execution.run_interface(db, interface.id, None, 1)
    single = execution.run_case(db, case.id, None, 1)
    chain = execution.run_chain(db, [case.id], None, 1)
    assert direct["passed"] and single["passed"] and chain[0]["passed"]
    assert secret not in json.dumps([direct, single, chain])
    assert secret not in json.dumps([row.detail for row in db.query(Report).all()])
    assert all(row["headers"]["Authorization"] == "Bearer " + secret for row in sent)
    assert db.get(Interface, interface.id).headers["Authorization"] == "Bearer " + secret


@pytest.mark.parametrize("secret", [13800000000, "synthetic-recording-secret"])
def test_raw_consumer_masks_same_field_and_cross_field_aliases(consumer, secret):
    _, calls = consumer
    original = {"method": "POST", "path": "/mock/1/echo", "project_id": 1,
                "request_headers": {}, "request_body": {"phone": secret, "echo": secret},
                "response_status": 200, "response_body": {"echo": secret}}
    before = deepcopy(original)
    result = traffic.record_traffic.apply(args=(original,), throw=False)
    assert result.state == "SUCCESS"
    saved = calls[0][1]
    assert saved["request_body"] == {"phone": "***", "echo": "***"}
    assert saved["response_body"] == {"echo": "***"}
    assert saved["project_id"] == 1 and saved["response_status"] == 200
    assert original == before


def test_recording_producer_masks_aliases_before_publish():
    # Execute the actual middleware without importing main.py (which bootstraps DBs).
    source = Path(__file__).resolve().parents[1] / "main.py"
    node = next(item for item in ast.parse(source.read_text(encoding="utf-8-sig")).body
                if isinstance(item, ast.AsyncFunctionDef) and item.name == "recording_middleware")
    node.decorator_list = []
    captured = []
    async def publish(task, record):
        captured.append(record)
    async def chunks():
        yield json.dumps({"echo": 13800000000}).encode()
    async def next_response(request):
        return SimpleNamespace(body_iterator=chunks(), headers={}, media_type="application/json", status_code=200)
    async def body():
        return json.dumps({"phone": 13800000000, "echo": 13800000000}).encode()
    namespace = {"Request": Request, "Response": Response, "RECORD_SKIP_PREFIXES": (),
                 "_safe_json": lambda raw: json.loads(raw) if raw else None,
                 "_extract_project_id": lambda request: 1, "TrafficRecordCreate": TrafficRecordCreate,
                 "_mask": redaction.mask_sensitive, "publish_recording": publish,
                 "record_traffic": object(), "recording_failure_monitor": SimpleNamespace(report=Mock())}
    namespace.update({name: value for name, value in vars(redaction).items() if not name.startswith("__")})
    namespace["_mask"] = redaction.mask_sensitive
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
    request = SimpleNamespace(url=SimpleNamespace(path="/mock/1/echo"), method="POST", headers={}, body=body)
    returned = asyncio.run(namespace["recording_middleware"](request, next_response))
    assert json.loads(returned.body) == {"echo": 13800000000}  # Never alter business response.
    assert len(captured) == 1
    assert captured[0]["request_body"]["echo"] == captured[0]["response_body"]["echo"] == "***"
