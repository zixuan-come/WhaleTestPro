from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

from app.core.bootstrap import ensure_perf_schema


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
