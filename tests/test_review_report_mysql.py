"""Opt-in MySQL evidence on UUID schemas created only on a disposable server."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.database import Base
from app.models import register_models
from app.models.user import User
from app.models.team import Team
from app.models.team_member import TeamMember
from app.models.project import Project
from app.models.execution_report import ExecutionReport
from app.models.report_folder import ReportFolder, ReportFolderItem
from app.services import report_management


ROOT = Path(__file__).resolve().parents[1]
ADMIN_URL = os.environ.get('WHALE_MYSQL_008_TEST_URL', '')
pytestmark = pytest.mark.skipif(
    not ADMIN_URL or os.environ.get('WHALE_MYSQL_008_ALLOW_CREATE_DROP') != '1',
    reason='Requires an explicitly enabled disposable MySQL server',
)


@pytest.fixture
def isolated_schema():
    register_models()
    url = make_url(ADMIN_URL)
    assert url.drivername == 'mysql+pymysql'
    admin = create_engine(url.set(database='mysql'), hide_parameters=True)
    name = 'review_fixes_' + uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4'))
    target = url.set(database=name)
    engine = create_engine(target, hide_parameters=True)
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(User(id=1, username='review-owner', hashed_password='unused')); db.flush()
            db.add(Team(id=1, name='review-team', owner_id=1)); db.flush()
            db.add(TeamMember(team_id=1, user_id=1, role='owner'))
            db.add(Project(id=1, name='review-project', team_id=1)); db.flush()
            db.add_all([ReportFolder(id=number, project_id=1, name=f'folder-{number}',
                                    name_key=f'folder-{number}') for number in (1, 2)])
            db.add(ExecutionReport(id=1, project_id=1, kind='case', name='synthetic run',
                                   status='completed', passed=True, created_at=datetime.utcnow()))
            db.commit()
        yield engine, target
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP DATABASE `{name}`'))
        admin.dispose()


def membership(db):
    return db.query(ReportFolderItem).filter_by(project_id=1, storage='run', report_id=1)


def test_current_read_replaces_stale_membership_after_other_move(isolated_schema):
    engine, _ = isolated_schema
    with Session(engine) as db:
        report_management.move_reports(db, 1, ['run-1'], 1)
    with Session(engine) as stale:
        assert stale.scalar(text('SELECT @@transaction_isolation')) == 'REPEATABLE-READ'
        before = membership(stale).one()
        assert before.folder_id == 1
        with Session(engine) as competing:
            report_management.move_reports(competing, 1, ['run-1'], 2)
        assert report_management.move_reports(stale, 1, ['run-1'], 1) == {'moved': 1, 'folder_id': 1}
    with Session(engine) as reader:
        assert membership(reader).one().folder_id == 1


def test_concurrent_first_moves_do_not_conflict_or_create_duplicate_memberships(isolated_schema):
    engine, _ = isolated_schema
    start = Barrier(2)
    def move(folder):
        with Session(engine) as db:
            db.query(Project).filter_by(id=1).one()  # Open an earlier RR snapshot.
            start.wait(timeout=10)
            return report_management.move_reports(db, 1, ['run-1'], folder)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(move, (1, 2)))
    assert [result['moved'] for result in results] == [1, 1]
    with Session(engine) as reader:
        assert membership(reader).count() == 1
        assert membership(reader).one().folder_id in (1, 2)


def test_standalone_mysql_migration_creates_missing_fk_tables_and_is_repeatable(isolated_schema, tmp_path):
    engine, url = isolated_schema
    for table in ('report_folder_item', 'report_folder', 'traffic_capture', 'execution_report'):
        with engine.begin() as connection:
            connection.execute(text(f'DROP TABLE `{table}`'))
    env = {**os.environ, 'PYTHONPATH': str(ROOT), 'DATABASE_URL': url.render_as_string(hide_password=False),
           'SHADOW_DATABASE_URL': url.render_as_string(hide_password=False),
           'SECRET_KEY': 'synthetic-disposable-migration-only'}
    for _ in range(2):
        result = subprocess.run([sys.executable, '-m', 'scripts.run_migrations'], cwd=tmp_path,
                                env=env, capture_output=True, text=True, timeout=45)
        assert result.returncode == 0, result.stderr
    assert {'execution_report', 'traffic_capture', 'report_folder', 'report_folder_item'}.issubset(
        inspect(engine).get_table_names())
    with Session(engine) as db:
        assert db.get(Project, 1).name == 'review-project'
        assert db.get(User, 1).username == 'review-owner'
