from contextlib import contextmanager
from contextvars import ContextVar

current_execution = ContextVar("current_execution", default=None)
execution_source = ContextVar("execution_source", default="manual")


def execution_id(project_id):
    current = current_execution.get()
    return current["id"] if current and current["project_id"] == project_id else None


def capture_attempt(evidence):
    current = current_execution.get()
    if current and current["kind"] == "case":
        current["attempts"].append(evidence)


def capture_steps(steps):
    current = current_execution.get()
    if current and current["kind"] == "scenario":
        current["steps"] = steps


@contextmanager
def triggered_by(source):
    token = execution_source.set(source)
    try:
        yield
    finally:
        execution_source.reset(token)
