"""Scheduled targets share the regression engine, without broker/network I/O."""
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text

from tests.test_execution_reports import reports, ExecutionReport, Case
from app.models.schedule import Schedule
from app.schemas.schedule import ScheduleCreate
from app.services import schedule as service
from app.tasks import schedule as tasks
from app.core.migrations import ensure_schedule_selection_schema


@pytest.mark.parametrize('mode,ids', [('case', [3, 1, 3]), ('suite', [1])])
def test_saved_selection_and_scheduled_report_use_current_regression_engine(reports, monkeypatch, mode, ids):
    _, db, calls = reports
    monkeypatch.setattr(service.scheduler, 'sync_schedule', lambda _: None)
    original_close = db.close
    monkeypatch.setattr(db, 'close', lambda: None)
    monkeypatch.setattr(tasks, 'SessionLocal', lambda: db)
    row = service.s_create(db, ScheduleCreate(name='每日订单回归', cron='0 2 * * *', env_id=1,
        selection={'mode': mode, 'ids': ids}), 1)
    assert row.selection['ids'] == list(dict.fromkeys(ids))
    result = tasks.scheduled_regression.run(project_id=1, schedule_id=row.id)
    assert result['report_id'].startswith('run-') and calls
    root = db.get(ExecutionReport, int(result['report_id'].split('-')[1]))
    assert root.kind == 'regression' and root.trigger_source == 'scheduled'
    assert root.name == '每日订单回归'
    original_close()


def test_disabled_or_deleted_schedule_is_not_executed_by_queued_message(reports, monkeypatch):
    _, db, calls = reports
    monkeypatch.setattr(db, 'close', lambda: None)
    monkeypatch.setattr(tasks, 'SessionLocal', lambda: db)
    row = Schedule(name='paused', cron='0 2 * * *', project_id=1, env_id=1,
        selection={'mode':'case','ids':[1]}, enabled=False)
    db.add(row); db.commit()
    for schedule_id in (row.id, 999):
        assert tasks.scheduled_regression.run(project_id=1, schedule_id=schedule_id)['skipped']
    assert not calls


def test_deleted_selected_case_cannot_expand_to_all_cases(reports, monkeypatch):
    _, db, calls = reports
    monkeypatch.setattr(db, 'close', lambda: None)
    monkeypatch.setattr(tasks, 'SessionLocal', lambda: db)
    row = Schedule(name='stale', cron='0 2 * * *', project_id=1, env_id=1,
        selection={'mode':'case','ids':[999]}, enabled=True)
    db.add(row); db.commit()
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        tasks.scheduled_regression.run(project_id=1, schedule_id=row.id)
    assert error.value.status_code == 404 and not calls


@pytest.mark.parametrize('targets', [{'mode':'case','ids':[]},{'mode':'suite','ids':[0]}])
def test_empty_or_invalid_selection_never_uses_legacy_all_cases(targets):
    with pytest.raises(ValidationError):
        ScheduleCreate(name='bad', cron='0 2 * * *', env_id=1, selection=targets)


def test_selection_cannot_be_mixed_with_legacy_filters():
    with pytest.raises(ValidationError):
        ScheduleCreate(name='bad', cron='0 2 * * *', env_id=1, tag='smoke', selection={'mode':'case','ids':[1]})


def test_selection_migration_is_idempotent_and_preserves_legacy_targets():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE schedule(id INTEGER PRIMARY KEY, tag VARCHAR(50), suite_id INTEGER)'))
        conn.execute(text("INSERT INTO schedule VALUES(1, 'smoke', NULL)"))
    ensure_schedule_selection_schema(engine); ensure_schedule_selection_schema(engine)
    with engine.connect() as conn:
        row = conn.execute(text('SELECT tag,suite_id,selection,notify FROM schedule')).one()
    assert tuple(row) == ('smoke', None, None, 0)
    engine.dispose()
