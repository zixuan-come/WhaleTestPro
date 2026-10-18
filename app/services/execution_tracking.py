"""Explicit execution ownership; never infer parentage from timestamps."""
from datetime import datetime
from functools import wraps
from inspect import signature
from time import perf_counter

from sqlalchemy.orm import Session

from app.core.execution_context import current_execution, execution_source
from app.core.redaction import mask_sensitive, sensitive_strings
from app.models.execution_report import ExecutionReport


def tracked(kind, *, include_report_id=False):
    def decorate(function):
        parameters = signature(function)

        @wraps(function)
        def run(*args, **kwargs):
            values = parameters.bind(*args, **kwargs)
            values.apply_defaults()
            values = values.arguments
            db, project_id = values["db"], values.get("project_id")
            # Repository-only adapters used by callers cannot persist execution
            # records. The application always supplies a real SQLAlchemy Session.
            if not isinstance(db, Session) or project_id is None:
                return function(*args, **kwargs)
            from app.repositories import case, suite, environment
            actual_kind = "scenario" if kind == "chain" else kind
            object_id = values.get(f"{actual_kind}_id")
            if kind in {"case", "suite"}:
                resource = (case if kind == "case" else suite).db_get(db, object_id, project_id)
                if resource is None:
                    return function(*args, **kwargs)
                name = resource.name
            elif kind == "chain":
                name = values.get("scenario_name") or "临时接口链路"
            else:
                name = values.get("report_name") or ("标签回归 · " + values["tag"] if values.get("tag") else "批量回归测试")
            env_id = values.get("env_id")
            env = environment.db_get(db, env_id, project_id) if env_id is not None else None
            if env_id is not None and env is None:
                return function(*args, **kwargs)
            secrets = sensitive_strings(env.variables or {}) if env else ()
            parent = current_execution.get()
            record = ExecutionReport(
                project_id=project_id, parent_id=parent["id"] if parent and parent["project_id"] == project_id else None,
                kind=actual_kind, object_id=object_id,
                name=mask_sensitive(name, secrets=secrets)[:100],
                trigger_source=execution_source.get(), environment_name=env.name if env else "未指定环境",
                created_at=datetime.utcnow(), status="running", passed=None,
            )
            db.add(record)
            db.commit()
            record_id = record.id
            state = {"id": record_id, "project_id": project_id, "kind": actual_kind, "attempts": []}
            token = current_execution.set(state)
            started = perf_counter()
            result = None
            raised = None
            try:
                result = function(*args, **kwargs)
                if include_report_id and isinstance(result, dict):
                    result["report_id"] = f"run-{record_id}"
                return result
            except Exception as exc:
                raised = exc
                db.rollback()
                raise
            finally:
                current_execution.reset(token)
                passed = (bool(result) and all(row.get("passed", False) for row in result)
                          if isinstance(result, list) else bool(result and result.get("passed", False)))
                if kind == "suite" and result:
                    passed = result["total"] > 0 and result["failed"] == 0
                detail = {"result": result}
                if state["attempts"]:
                    detail["attempts"] = state["attempts"]
                if "steps" in state:
                    detail["steps"] = state["steps"]
                if raised:
                    detail = {"error": f"执行异常（{type(raised).__name__}）"}
                db.query(ExecutionReport).filter(
                    ExecutionReport.id == record_id, ExecutionReport.project_id == project_id,
                ).update({"passed": False if raised else passed, "status": "error" if raised else "completed",
                          "duration_ms": round((perf_counter() - started) * 1000), "detail": detail},
                         synchronize_session=False)
                db.commit()
        return run
    return decorate
