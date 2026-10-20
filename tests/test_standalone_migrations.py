"""Migration entry point in a fresh interpreter, without app/test model imports."""
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import create_engine, inspect, text


ROOT = Path(__file__).resolve().parents[1]


def test_standalone_entry_upgrades_both_legacy_databases_in_fresh_process(tmp_path):
    urls = [f"sqlite:///{tmp_path / name}" for name in ("main.sqlite", "shadow.sqlite")]
    for url in urls:
        engine = create_engine(url)
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE project (id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE test_report (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL)"))
            connection.execute(text("INSERT INTO project VALUES (1)"))
            connection.execute(text("INSERT INTO users VALUES (3)"))
            connection.execute(text("INSERT INTO test_report VALUES (7, 1)"))
        engine.dispose()
    env = {**os.environ, "PYTHONPATH": str(ROOT), "DATABASE_URL": urls[0],
           "SHADOW_DATABASE_URL": urls[1], "SECRET_KEY": "synthetic-standalone-migration-test-only"}
    # A private cwd means pydantic cannot discover the repository's .env.
    for _ in range(2):
        result = subprocess.run([sys.executable, "-m", "scripts.run_migrations"], cwd=tmp_path,
                                env=env, capture_output=True, text=True, timeout=45)
        assert result.returncode == 0, result.stderr
        assert "NoReferencedTableError" not in result.stderr
    for url in urls:
        engine = create_engine(url)
        assert {"execution_report", "project_notification", "traffic_capture", "report_folder",
                "report_folder_item"}.issubset(inspect(engine).get_table_names())
        with engine.connect() as connection:
            assert connection.execute(text("SELECT id FROM test_report")).all() == [(7,)]
            assert connection.execute(text("SELECT id FROM users")).all() == [(3,)]
            assert connection.execute(text("SELECT execution_report_id FROM test_report")).all() == [(None,)]
        engine.dispose()
