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
