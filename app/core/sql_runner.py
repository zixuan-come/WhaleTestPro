import re

from sqlalchemy import text


_SINGLE_DML = re.compile(r"^\s*(?:insert|update|delete)\b", re.IGNORECASE)
_FORBIDDEN = re.compile(r"\b(?:alter|create|drop|grant|revoke|truncate|rename|replace|load|outfile|dumpfile|call|do|handler|lock|unlock)\b", re.IGNORECASE)
_PROTECTED_TABLES = {
    "users", "project", "project_member", "interface", "test_case", "test_report",
    "environment", "mock", "perf_tasks", "schedule", "scenario", "scenario_report",
    "scenario_report_step", "traffic_records", "team", "team_member", "team_invitation",
    "team_permission", "demo_orders",
}

def validate_setup_sql(sql):
    """Allow only one data-change statement for test setup/teardown."""
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("setup/teardown SQL 必须是非空的 INSERT、UPDATE 或 DELETE 语句")
    normalized = sql.strip()
    if normalized.endswith(";"):
        normalized = normalized[:-1].rstrip()
    if ";" in normalized or not _SINGLE_DML.match(normalized) or _FORBIDDEN.search(normalized):
        raise ValueError("setup/teardown SQL 只允许单条 INSERT、UPDATE 或 DELETE 语句")
    referenced = re.findall(r"(?:from|into|update|join)\s+((?:[a-zA-Z_][a-zA-Z0-9_]*\.)?[a-zA-Z_][a-zA-Z0-9_]*)", normalized, re.IGNORECASE)
    if any(name.lower().split(".")[-1] in _PROTECTED_TABLES for name in referenced):
        raise ValueError("setup/teardown SQL 不允许修改平台业务表")
    return normalized

def run_sql(db, statements):
    for sql in statements or []:
        db.execute(text(validate_setup_sql(sql)))
    db.commit()





