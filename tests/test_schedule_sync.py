from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.project import Project
from app.models.schedule import Schedule
from app.models.schedule_sync_outbox import ScheduleSyncOutbox
from app.models.suite import TestSuite  # noqa: F401  schedule.suite_id target
from app.models.team import Team
from app.models.team_member import TeamMember
from app.models.user import User
from app.models.environment import Environment
from app.schemas.schedule import ScheduleCreate
from app.services import schedule as schedule_service


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User(username="schedule-owner", hashed_password="x")
    db.add(user)
    db.flush()
    team = Team(name="schedule-team", owner_id=user.id)
    db.add(team)
    db.flush()
    db.add(TeamMember(team_id=team.id, user_id=user.id, role="owner"))
    project = Project(name="schedule-project", team_id=team.id)
    db.add(project)
    db.flush()
    db.add(Environment(id=1, name="local", base_url="http://app:8000", project_id=project.id))
    db.commit()
    return db, project.id


def _schedule_data(cron="0 0 * * *"):
    return ScheduleCreate(name="daily", cron=cron, enabled=True, env_id=1)


def test_create_schedule_clears_outbox_after_redbeat_sync(monkeypatch):
    db, project_id = _db()
    synchronized = []
    monkeypatch.setattr(
        schedule_service.scheduler,
        "sync_schedule",
        lambda schedule: synchronized.append(schedule.id),
    )

    result = schedule_service.s_create(db, _schedule_data(), project_id)

    assert synchronized == [result.id]
    assert result.sync_status == "synced"
    assert db.get(ScheduleSyncOutbox, result.id) is None


def test_failed_redbeat_sync_is_persisted_and_retried(monkeypatch):
    db, project_id = _db()

    def fail(_schedule):
        raise OSError("redis unavailable")

    monkeypatch.setattr(schedule_service.scheduler, "sync_schedule", fail)
    result = schedule_service.s_create(db, _schedule_data(), project_id)

    assert result.sync_status == "error"
    event = db.get(ScheduleSyncOutbox, result.id)
    assert event is not None
    assert event.action == "sync"
    assert event.attempts == 1

    monkeypatch.setattr(schedule_service.scheduler, "sync_schedule", lambda _schedule: None)
    assert schedule_service.reconcile_pending(db) == {"synced": 1, "failed": 0}
    assert db.get(ScheduleSyncOutbox, result.id) is None
    assert db.get(Schedule, result.id).sync_status == "synced"


def test_delete_schedule_keeps_retry_event_when_redbeat_is_down(monkeypatch):
    db, project_id = _db()
    monkeypatch.setattr(schedule_service.scheduler, "sync_schedule", lambda _schedule: None)
    schedule = schedule_service.s_create(db, _schedule_data(), project_id)

    def fail(_schedule_id):
        raise OSError("redis unavailable")

    monkeypatch.setattr(schedule_service.scheduler, "remove_schedule", fail)
    deleted = schedule_service.s_delete(db, schedule.id, project_id)

    assert deleted.id == schedule.id
    assert db.get(Schedule, schedule.id) is None
    event = db.get(ScheduleSyncOutbox, schedule.id)
    assert event is not None
    assert event.action == "delete"

    monkeypatch.setattr(schedule_service.scheduler, "remove_schedule", lambda _schedule_id: None)
    assert schedule_service.reconcile_pending(db) == {"synced": 1, "failed": 0}
    assert db.get(ScheduleSyncOutbox, schedule.id) is None
