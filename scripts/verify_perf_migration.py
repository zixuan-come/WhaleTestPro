"""Opt-in additive MySQL migration check on an isolated disposable server."""
import os
import sys
import time
from pathlib import Path
from sqlalchemy import create_engine, inspect, text

if os.environ.get("WHALE_LOAD_VERIFY_ALLOW") != "isolated-fixture":
    raise SystemExit("Explicit isolated opt-in required")

os.environ.update(DATABASE_URL="sqlite:///:memory:", SHADOW_DATABASE_URL="sqlite:///:memory:",
                  SECRET_KEY="isolated-migration-verification-not-real-credential")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.migrations import ensure_perf_load_plan_schema

url = "mysql+pymysql://root:synthetic-migration-only@load-check-mysql:3306/"
server = create_engine(url, pool_pre_ping=True)
deadline = time.monotonic() + 55
while True:
    try:
        with server.connect() as connection:
            connection.execute(text("SELECT 1"))
        break
    except Exception:
        if time.monotonic() > deadline:
            raise RuntimeError("Isolated MySQL readiness timeout") from None
        time.sleep(1)

for name in ("load_check_main", "load_check_shadow"):
    with server.begin() as connection:
        connection.execute(text(f"CREATE DATABASE {name}"))
    engine = create_engine(url + name)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE perf_tasks(id INT PRIMARY KEY, target_path VARCHAR(255), status VARCHAR(50))"))
        connection.execute(text("INSERT INTO perf_tasks VALUES(1, '/old', 'done')"))
    ensure_perf_load_plan_schema(engine)
    ensure_perf_load_plan_schema(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("perf_tasks")}
    assert columns == {"id", "target_path", "status", "load_config", "iteration_stats"}
    with engine.begin() as connection:
        old = connection.execute(text("SELECT * FROM perf_tasks WHERE id=1")).one()
        assert tuple(old) == (1, "/old", "done", None, None)
        connection.execute(text("UPDATE perf_tasks SET load_config=JSON_OBJECT('mode','chain'), iteration_stats=JSON_OBJECT('iterations',2) WHERE id=1"))
        assert connection.execute(text("SELECT JSON_EXTRACT(load_config,'$.mode') FROM perf_tasks")).scalar_one() == '"chain"'
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migration WHERE version='012_perf_load_plan'")).scalar_one() == 1
    engine.dispose()
server.dispose()
print("Isolated MySQL 8: both databases passed additive migration, repeat execution, old-row preservation, JSON round-trip")
