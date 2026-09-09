"""Project authorization vocabulary and configurable team permissions."""

from enum import Enum
from typing import Literal


class Resource(str, Enum):
    PROJECT = "project"
    PROJECT_MEMBER = "project_member"
    INTERFACE = "interface"
    CASE = "case"
    ENVIRONMENT = "environment"
    MOCK = "mock"
    SCHEDULE = "schedule"
    PERF = "perf"
    SCENARIO = "scenario"
    SUITE = "suite"
    REPORT = "report"
    TRAFFIC = "traffic"
    REGRESSION = "regression"


class Action(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    MANAGE = "manage"
    OWNER = "owner"


PermissionKey = Literal[
    "interface.write",
    "case.write",
    "environment.write",
    "mock.write",
    "schedule.write",
    "perf.write",
    "scenario.write",
    "suite.write",
]

TEAM_PERMISSION_KEYS: tuple[PermissionKey, ...] = (
    "interface.write",
    "case.write",
    "environment.write",
    "mock.write",
    "schedule.write",
    "perf.write",
    "scenario.write",
    "suite.write",
)

WRITE_PERMISSION_BY_RESOURCE: dict[Resource, PermissionKey] = {
    Resource.INTERFACE: "interface.write",
    Resource.CASE: "case.write",
    Resource.ENVIRONMENT: "environment.write",
    Resource.MOCK: "mock.write",
    Resource.SCHEDULE: "schedule.write",
    Resource.PERF: "perf.write",
    Resource.SCENARIO: "scenario.write",
    Resource.SUITE: "suite.write",
}
