"""Evidence-only redaction, using synthetic secrets and memory databases."""
import json
from urllib.parse import quote, quote_plus

import pytest
import requests

from app.core.redaction import mask_sensitive
from app.models.case import Case
from app.models.interface import Interface
from app.models.report import TestReport as Report
from app.services import execution
from tests.test_suite_service import db


SECRET = "synthetic/key+with space?凭证"


def response(body, headers=None):
    item = requests.Response()
    item.status_code = 200
    item._content = json.dumps(body, ensure_ascii=False).encode("utf-8")
    item.headers.update(headers or {})
    return item


@pytest.mark.parametrize("encoded", [quote(SECRET, safe=""), quote_plus(SECRET),
                                    quote(SECRET, safe="").replace("%2F", "%2f"),
                                    quote(quote(SECRET, safe=""), safe=""),
                                    quote(quote(SECRET, safe="").replace("%2F", "%2f"), safe="")])
def test_known_secret_url_encodings_are_removed(encoded):
    evidence = {"error": "request failed: https://target.invalid/?session=" + encoded,
                "unrelated": "business-identifier", "passed": False}
    safe = mask_sensitive(evidence, secrets=(SECRET,))
    assert encoded not in safe["error"]
    assert "***" in safe["error"]
    assert safe["unrelated"] == evidence["unrelated"] and safe["passed"] is False
    assert encoded in evidence["error"]


@pytest.mark.parametrize("secret", [SECRET, 200])
@pytest.mark.parametrize("datasets", [False, True])
def test_single_case_alias_assertions_are_masked_without_changing_execution(db, monkeypatch, secret, datasets):
    interface = Interface(name="safe", method="GET", url="/safe", project_id=1,
                          headers={"X-Session": "${session}"})
    db.add(interface)
    db.flush()
    case = Case(name="safe", interface_id=interface.id, expected_status=200, project_id=1,
                assertions=[{"type": "json_eq", "path": "$.session", "expected": secret}],
                datasets=[{"phone": secret, "session": secret}] if datasets else None)
    db.add(case)
    db.commit()
    context = {"phone": secret, "session": secret, "base_url": "https://target.invalid"}
    monkeypatch.setattr(execution, "_env_context", lambda *a: context)
    sent = []
    def request(*args, **kwargs):
        sent.append(kwargs)
        return response({"session": secret})
    monkeypatch.setattr(execution, "_request", request)
    result = execution.run_case(db, case.id, None, 1)
    detail = result[0] if datasets else result
    assert detail["passed"] is True and detail["attempts"] == 1
    assert detail["actual_status"] == detail["expected_status"] == 200
    assert detail["assertions"] == [{"type": "json_eq", "passed": True,
                                     "expected": "***", "actual": "***"}]
    assert sent[0]["headers"]["X-Session"] == str(secret)
    assert context["session"] == secret and context["phone"] == secret
    report = db.query(Report).one()
    assert report.case_id == case.id and report.passed is True and report.detail == result
    assert db.get(Case, case.id).assertions[0]["expected"] == secret


@pytest.mark.parametrize("phase", ["request", "teardown"])
def test_single_case_encoded_errors_are_safe_even_on_failure(db, monkeypatch, phase):
    interface = Interface(name="safe", method="GET", url="/safe", project_id=1)
    db.add(interface)
    db.flush()
    case = Case(name="safe", interface_id=interface.id, expected_status=200,
                project_id=1, teardown_sql="cleanup" if phase == "teardown" else None)
    db.add(case)
    db.commit()
    encoded = quote_plus(SECRET)
    monkeypatch.setattr(execution, "_env_context", lambda *a: {"token": SECRET})
    def failure(*args, **kwargs):
        raise RuntimeError("synthetic error: session=" + encoded)
    monkeypatch.setattr(execution, "_request", failure if phase == "request"
                        else lambda *a, **k: response({"ok": True}))
    if phase == "teardown":
        monkeypatch.setattr(execution, "run_sql",
                            lambda db, sql: failure() if sql == "cleanup" else None)
    result = execution.run_case(db, case.id, None, 1)
    assert result["passed"] is False
    assert encoded not in json.dumps(result) and "***" in json.dumps(result)
    assert db.query(Report).one().detail == result


@pytest.mark.parametrize("mode", ["interface", "chain"])
def test_encoded_error_and_echo_aliases_are_safe_in_other_execution_modes(db, monkeypatch, mode):
    interface = Interface(name="safe", method="GET", url="/safe/${token}", project_id=1,
                          headers={"X-Session": "${token}"})
    db.add(interface)
    db.flush()
    case = Case(name="safe", interface_id=interface.id, expected_status=200, project_id=1)
    db.add(case)
    db.commit()
    monkeypatch.setattr(execution, "_env_context", lambda *a: {"token": SECRET})
    sent = []
    def request(*a, **k):
        sent.append(k)
        raise requests.ConnectionError("session=" + quote_plus(SECRET))
    monkeypatch.setattr(execution, "_request", request)
    result = (execution.run_interface(db, interface.id, None, 1) if mode == "interface"
              else execution.run_chain(db, [case.id], None, 1))
    assert SECRET not in json.dumps(result, ensure_ascii=False)
    assert quote_plus(SECRET) not in json.dumps(result)
    assert sent[0]["headers"]["X-Session"] == SECRET
    if mode == "chain":
        assert quote_plus(SECRET) not in json.dumps(db.query(Report).one().detail)
    else:
        assert db.query(Report).count() == 0


@pytest.mark.parametrize("source", ["request", "response"])
def test_sensitive_request_literal_and_response_source_mask_single_case_alias(db, monkeypatch, source):
    interface = Interface(name="safe", method="POST", url="/safe", project_id=1,
                          body={"password": SECRET} if source == "request" else {"session": SECRET})
    db.add(interface)
    db.flush()
    case = Case(name="safe", interface_id=interface.id, expected_status=200, project_id=1,
                assertions=[{"type": "json_eq", "path": "$.session", "expected": SECRET}])
    db.add(case)
    db.commit()
    calls = []
    monkeypatch.setattr(execution, "_request", lambda *a, **k:
                        calls.append(k) or response({"token": SECRET, "session": SECRET}
                                                   if source == "response" else {"session": SECRET}))
    result = execution.run_case(db, case.id, None, 1)
    assert result["passed"] is True and result["assertions"][0]["actual"] == "***"
    assert calls[0]["json"]["password" if source == "request" else "session"] == SECRET


def test_known_alias_is_redacted_before_response_truncation(db, monkeypatch):
    interface = Interface(name="safe", method="GET", url="/safe", project_id=1)
    db.add(interface)
    db.commit()
    monkeypatch.setattr(execution, "_env_context", lambda *a: {"token": SECRET})
    body = {"prefix": "x" * 65490, "session": SECRET * 20}
    monkeypatch.setattr(execution, "_request", lambda *a, **k: response(body))
    result = execution.run_interface(db, interface.id, None, 1)
    assert result["passed"] is True and result["response"]["body_truncated"] is True
    assert "synthetic/key" not in result["response"]["body"]
