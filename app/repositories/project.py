from sqlalchemy import and_
from sqlalchemy.orm import Session
from app.models.case import Case
from app.models.environment import Environment
from app.models.interface import Interface
from app.models.mock import Mock
from app.models.perf import PerfTask, PerfRun
from app.models.project import Project
from app.models.team_member import TeamMember
from app.models.report import TestReport
from app.models.scenario import Scenario
from app.models.scenario_report import ScenarioReport, ScenarioReportStep
from app.models.schedule import Schedule
from app.models.traffic_record import TrafficRecord
from app.models.traffic_capture import TrafficCapture
from app.models.suite import TestSuite
from app.models.execution_report import ExecutionReport
from app.repositories import schedule_sync as schedule_sync_repo
from app.schemas.project import ProjectCreate


def db_create(db: Session, project: ProjectCreate) -> Project:
    values = project.model_dump(exclude_none=True)
    team_id = values.pop("team_id")
    db_project = Project(**values, team_id=team_id)
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project


def db_get(db: Session, project_id: int) -> Project | None:
    return db.query(Project).filter(Project.id == project_id).first()


def db_get_for_user(db: Session, project_id: int, user_id: int) -> Project | None:
    return (
        db.query(Project)
        .join(
            TeamMember,
            and_(TeamMember.team_id == Project.team_id, TeamMember.user_id == user_id),
        )
        .filter(Project.id == project_id)
        .first()
    )


def db_list_for_user(db: Session, user_id: int, team_id: int | None = None) -> list[Project]:
    query = (
        db.query(Project)
        .join(
            TeamMember,
            and_(TeamMember.team_id == Project.team_id, TeamMember.user_id == user_id),
        )
    )
    if team_id is not None:
        query = query.filter(Project.team_id == team_id)
    return query.order_by(Project.created_at.desc()).all()


def db_update(db: Session, project_id: int, project) -> Project | None:
    db_project = db.query(Project).filter(Project.id == project_id).first()
    if db_project is None:
        return None
    for key, value in project.model_dump(exclude={"team_id"}, exclude_unset=True).items():
        setattr(db_project, key, value)
    db.commit()
    db.refresh(db_project)
    return db_project


class ProjectPerfBusyError(RuntimeError):
    pass


def db_lock_project(db: Session, project_id: int) -> Project | None:
    # A locking current read avoids stale REPEATABLE READ/identity-map snapshots.
    return (db.query(Project).filter(Project.id == project_id)
            .populate_existing().with_for_update().first())


def db_delete(db: Session, project_id: int, check_perf=None) -> Project | None:
    db_project = db_lock_project(db, project_id)
    if db_project is None:
        db.rollback()
        return None
    try:
        perf_tasks = (db.query(PerfTask).filter(PerfTask.project_id == project_id)
                      .populate_existing().with_for_update().all())
        if any(task.status in {"queued", "running"} for task in perf_tasks):
            raise ProjectPerfBusyError("项目仍有排队或运行中的压测，请先停止并清理后再删除")
        if check_perf is not None:
            check_perf(project_id)
        schedule_ids = [
            schedule_id
            for (schedule_id,) in (
                db.query(Schedule.id)
                .filter(Schedule.project_id == project_id)
                .all()
            )
        ]
        for schedule_id in schedule_ids:
            schedule_sync_repo.db_enqueue_delete(db, schedule_id)
        report_ids = db.query(ScenarioReport.id).filter(ScenarioReport.project_id == project_id)
        db.query(ScenarioReportStep).filter(ScenarioReportStep.report_id.in_(report_ids)).delete(synchronize_session=False)
        # schedule/test_report 先于 test_suite 删除，因为二者都可能通过
        # suite_id 外键引用测试套件。
        for model in (
            Schedule,
            ExecutionReport,
            Case,
            Interface,
            Environment,
            Mock,
            PerfRun,
            PerfTask,
            TestReport,
            ScenarioReport,
            Scenario,
            TrafficRecord,
            TrafficCapture,
            TestSuite,
        ):
            db.query(model).filter(model.project_id == project_id).delete(synchronize_session=False)
        db.delete(db_project)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return db_project
