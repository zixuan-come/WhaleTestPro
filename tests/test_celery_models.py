import subprocess
import sys


def test_celery_worker_registers_project_before_traffic_record_fk_resolution():
    """Worker 独立启动时也必须能解析 TrafficRecord.project_id 外键。"""
    script = """
from app.core.celery_app import celery_app
from app.database import Base

assert celery_app is not None
foreign_key = next(iter(Base.metadata.tables[\"traffic_records\"].foreign_keys))
assert foreign_key.column.table.name == \"project\"
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
