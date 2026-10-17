from copy import deepcopy
from types import SimpleNamespace


def with_request_overrides(interface, overrides):
    """Build an execution-only copy, preserving empty values and explicit clears."""
    if overrides is None:
        return interface
    allowed = {"path_params", "headers", "params", "body"}
    if not isinstance(overrides, dict) or set(overrides) - allowed:
        raise ValueError("用例请求配置只支持 Path、Query、Headers 和 Body")
    fields = {name: getattr(interface, name, None)
              for name in ("id", "name", "method", "url", *sorted(allowed))}
    fields.update(overrides)
    return SimpleNamespace(**deepcopy(fields))
