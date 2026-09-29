from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.models.suite import TestSuite


PERF_SCHEMA_COLUMNS = {
    "p95_response_ms": "FLOAT NULL",
    "p99_response_ms": "FLOAT NULL",
    "request_stats": "JSON NULL",
    "error_summary": "JSON NULL",
    "history_samples": "JSON NULL",
}

TEST_SUITE_SCHEMA_COLUMNS = {
    "schedule": {
        "suite_id": "INTEGER NULL",
    },
    "test_report": {
        "suite_id": "INTEGER NULL",
        "suite_name": "VARCHAR(100) NULL",
        "execution_type": "VARCHAR(20) NULL",
    },
}

TEST_SUITE_SCHEMA_INDEXES = {
    "schedule": ("idx_schedule_suite", "suite_id"),
    "test_report": ("idx_report_suite", "suite_id"),
}

TEST_SUITE_SCHEMA_FOREIGN_KEYS = {
    "schedule": ("fk_schedule_suite", "suite_id"),
    "test_report": ("fk_report_suite", "suite_id"),
}

USERNAME_MAX_LENGTH = 20


def _has_single_column_index(inspector, table_name: str, column_name: str) -> bool:
    return any(index.get("column_names") == [column_name] for index in inspector.get_indexes(table_name))


def _has_test_suite_foreign_key(inspector, table_name: str, column_name: str) -> bool:
    return any(
        foreign_key.get("constrained_columns") == [column_name]
        and foreign_key.get("referred_table") == "test_suite"
        and foreign_key.get("referred_columns") == ["id"]
        for foreign_key in inspector.get_foreign_keys(table_name)
    )


def ensure_test_suite_schema(bind) -> None:
    """Idempotently upgrade legacy databases for test suites."""
    TestSuite.__table__.create(bind=bind, checkfirst=True)
    preparer = bind.dialect.identifier_preparer

    with bind.begin() as connection:
        inspector = inspect(connection)
        for table_name, columns in TEST_SUITE_SCHEMA_COLUMNS.items():
            if not inspector.has_table(table_name):
                continue
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            quoted_table = preparer.quote(table_name)
            for column_name, column_type in columns.items():
                if column_name not in existing:
                    quoted_column = preparer.quote(column_name)
                    connection.execute(
                        text(f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_column} {column_type}")
                    )

    with bind.begin() as connection:
        inspector = inspect(connection)
        for table_name, (index_name, column_name) in TEST_SUITE_SCHEMA_INDEXES.items():
            if not inspector.has_table(table_name):
                continue
            if not _has_single_column_index(inspector, table_name, column_name):
                connection.execute(
                    text(
                        f"CREATE INDEX {preparer.quote(index_name)} "
                        f"ON {preparer.quote(table_name)} ({preparer.quote(column_name)})"
                    )
                )

    if bind.dialect.name != "mysql":
        return

    with bind.begin() as connection:
        inspector = inspect(connection)
        for table_name, (constraint_name, column_name) in TEST_SUITE_SCHEMA_FOREIGN_KEYS.items():
            if not inspector.has_table(table_name):
                continue
            if not _has_test_suite_foreign_key(inspector, table_name, column_name):
                connection.execute(
                    text(
                        f"ALTER TABLE {preparer.quote(table_name)} "
                        f"ADD CONSTRAINT {preparer.quote(constraint_name)} "
                        f"FOREIGN KEY ({preparer.quote(column_name)}) "
                        "REFERENCES test_suite (id)"
                    )
                )


def ensure_user_schema(bind) -> None:
    """Idempotently align the MySQL username column with the 4-20 domain rule."""
    if bind.dialect.name != "mysql":
        return

    with bind.begin() as connection:
        inspector = inspect(connection)
        if not inspector.has_table("users"):
            return

        username_column = next(
            (column for column in inspector.get_columns("users") if column["name"] == "username"),
            None,
        )
        if username_column is None:
            raise RuntimeError("users.username 字段不存在，无法执行用户名长度迁移")

        current_length = getattr(username_column["type"], "length", None)
        if current_length == USERNAME_MAX_LENGTH and not username_column.get("nullable", True):
            return

        over_limit = connection.execute(
            text(
                "SELECT COUNT(*) FROM `users` "
                "WHERE CHAR_LENGTH(`username`) > :max_length"
            ),
            {"max_length": USERNAME_MAX_LENGTH},
        ).scalar_one()
        if over_limit:
            raise RuntimeError(
                f"users 表存在 {over_limit} 个超过 {USERNAME_MAX_LENGTH} 字符的用户名，"
                "请先清理历史数据再迁移"
            )

        connection.execute(
            text(
                "ALTER TABLE `users` "
                f"MODIFY COLUMN `username` VARCHAR({USERNAME_MAX_LENGTH}) NOT NULL"
            )
        )


def ensure_perf_schema(db: Session) -> None:
    """为已有数据库补齐压测观测字段，避免 create_all 升级时漏列。"""
    bind = db.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("perf_tasks"):
        return
    existing = {column["name"] for column in inspector.get_columns("perf_tasks")}
    missing = [name for name in PERF_SCHEMA_COLUMNS if name not in existing]
    for name in missing:
        db.execute(text(f"ALTER TABLE perf_tasks ADD COLUMN {name} {PERF_SCHEMA_COLUMNS[name]}"))
    if missing:
        db.commit()
