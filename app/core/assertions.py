import re

from sqlalchemy import text
from app.core.sql_database import test_sql_session
from app.core.variables import extract_match
from jsonschema import validate
from jsonschema.exceptions import ValidationError
from app.core.redaction import MASK, is_sensitive_source, mask_sensitive


_READ_ONLY_SQL = re.compile(r"^\s*select\b", re.IGNORECASE)
_FORBIDDEN_SQL = re.compile(
    r"\b(?:insert|update|delete|drop|alter|truncate|create|replace|grant|revoke|call|do|load|outfile|dumpfile|into)\b",
    re.IGNORECASE,
)


def _execute_read_only(db, sql):
    """Execute a conservative, single-statement SELECT for db_eq assertions."""
    if not isinstance(sql, str) or not _READ_ONLY_SQL.match(sql):
        raise ValueError("db_eq 只允许执行单条只读 SELECT 语句")
    if ";" in sql or _FORBIDDEN_SQL.search(sql):
        raise ValueError("db_eq 只允许执行单条只读 SELECT 语句")
    # A read-only query can still steal platform data; never execute on db.
    with test_sql_session() as tested_db:
        return tested_db.execute(text(sql)).scalar()


def run_assertions(response, assertions, db):
    results = []
    for a in assertions or []:
        a_type = a["type"]
        sensitive = is_sensitive_source(a.get("path") or a.get("sql"))
        try:
            if a_type in {"json_eq", "json_contains", "json_gt", "json_lt"}:
                match = extract_match(response.json(), a["path"])
                actual = match.value
                # Wildcards can select a secret without spelling its key.
                sensitive = sensitive or is_sensitive_source(str(match.full_path))
            if a_type == "json_eq":
                passed = actual == a["expected"]
            elif a_type == "json_contains":
                passed = a["expected"] in actual
            elif a_type == "json_gt":
                passed = actual > a["expected"]
            elif a_type == "json_lt":
                passed = actual < a["expected"]
            elif a_type == "response_time_lt":
                actual = response.elapsed.total_seconds() * 1000
                passed = actual < a["expected"]
            elif a_type == "header_eq":
                actual = response.headers.get(a["path"])
                passed = actual == a["expected"]
            elif a_type == "header_contains":
                actual = response.headers.get(a["path"])
                passed = a["expected"] in actual
            elif a_type == "json_schema":
                validate(instance=response.json(), schema=a["expected"])
                actual = "schema 校验通过"
                passed = True
            elif a_type == "db_eq":
                actual = _execute_read_only(db, a["sql"])
                passed = actual == a["expected"]
            else:
                actual = f"未知断言类型: {a_type}"
                passed = False
        except ValidationError as e:
            # e.message can embed original credentials.
            actual = f"schema 校验失败: {e.validator}"
            passed = False
        except Exception as e:
            actual = f"断言执行出错: {type(e).__name__}"
            passed = False

        results.append({
            "type": a_type,
            "passed": passed,
            "expected": MASK if sensitive else mask_sensitive(a.get("expected")),
            "actual": MASK if sensitive else mask_sensitive(actual),
        })

    return results
