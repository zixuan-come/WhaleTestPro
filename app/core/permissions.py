"""Canonical team permission keys and project route mapping."""

from typing import Literal


PermissionKey = Literal[
    "interface.write",
    "case.write",
    "environment.write",
    "mock.write",
    "schedule.write",
    "perf.write",
    "scenario.write",
]

TEAM_PERMISSION_KEYS: tuple[PermissionKey, ...] = (
    "interface.write",
    "case.write",
    "environment.write",
    "mock.write",
    "schedule.write",
    "perf.write",
    "scenario.write",
)

PROJECT_WRITE_PERMISSION_PREFIXES: tuple[tuple[str, PermissionKey], ...] = (
    ("/interfaces", "interface.write"),
    ("/cases", "case.write"),
    ("/environments", "environment.write"),
    ("/mocks", "mock.write"),
    ("/schedules", "schedule.write"),
    ("/perf/tasks", "perf.write"),
    ("/scenarios", "scenario.write"),
)


def is_execution_path(path: str) -> bool:
    return (
        path.startswith("/traffic/replay/")
        or path.startswith("/regression")
        or path.endswith(("/run", "/chain"))
    )


def permission_for_project_path(path: str) -> PermissionKey | None:
    for prefix, permission in PROJECT_WRITE_PERMISSION_PREFIXES:
        if path.startswith(prefix):
            return permission
    return None
