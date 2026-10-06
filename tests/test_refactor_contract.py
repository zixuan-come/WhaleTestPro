"""Characterization checks for extracted request/control/statistics helpers."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.services import execution


def test_request_field_helper_keeps_render_order_and_live_secrets(monkeypatch):
    interface = SimpleNamespace(headers={"Authorization": "Bearer synthetic-token"},
                                params={"page": 1}, body={"password": "synthetic-password"})
    before = deepcopy(vars(interface))
    seen = []
    def render(value, context):
        seen.append(value)
        assert context == {"marker": 17}
        return deepcopy(value)
    monkeypatch.setattr(execution, "render_deep", render)
    secrets = {"previous-step-secret"}
    fields = execution._render_request_fields(interface, {"marker": 17}, secrets)
    assert seen == [interface.headers, interface.params, interface.body]
    assert fields == {"headers": interface.headers, "params": interface.params, "json": interface.body}
    assert fields["json"]["password"] == "synthetic-password"
    assert {"synthetic-token", "synthetic-password", "previous-step-secret"} <= secrets
    assert vars(interface) == before


def test_request_field_helper_preserves_none_fields():
    interface = SimpleNamespace(headers=None, params=None, body=None)
    secrets = set()
    assert execution._render_request_fields(interface, {}, secrets) == {
        "headers": None, "params": None, "json": None,
    }
    assert not secrets
