from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

from app.core.bootstrap import ensure_perf_schema, ensure_test_suite_schema


def test_ensure_perf_schema_adds_missing_observability_columns():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE perf_tasks (id INTEGER PRIMARY KEY, name VARCHAR(100))"))

    db = sessionmaker(bind=engine)()
    try:
        ensure_perf_schema(db)
        columns = {column["name"] for column in inspect(engine).get_columns("perf_tasks")}
        assert {
            "p95_response_ms",
            "p99_response_ms",
            "request_stats",
            "error_summary",
            "history_samples",
        } <= columns
    finally:
        db.close()


def test_ensure_test_suite_schema_upgrades_main_and_shadow_idempotently():
    engines = [create_engine("sqlite:///:memory:"), create_engine("sqlite:///:memory:")]
    for engine in engines:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE project (id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE schedule (id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE test_report (id INTEGER PRIMARY KEY)"))

        ensure_test_suite_schema(engine)
        ensure_test_suite_schema(engine)

        inspector = inspect(engine)
        assert inspector.has_table("test_suite")
        assert {"suite_id"} <= {
            column["name"] for column in inspector.get_columns("schedule")
        }
        assert {"suite_id", "suite_name", "execution_type"} <= {
            column["name"] for column in inspector.get_columns("test_report")
        }
        assert any(
            index["column_names"] == ["suite_id"]
            for index in inspector.get_indexes("schedule")
        )
        assert any(
            index["column_names"] == ["suite_id"]
            for index in inspector.get_indexes("test_report")
        )
