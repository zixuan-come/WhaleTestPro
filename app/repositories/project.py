from sqlalchemy import and_
from sqlalchemy.orm import Session
from app.models.case import Case
from app.models.environment import Environment
from app.models.interface import Interface
from app.models.mock import Mock
from app.models.perf import PerfTask
from app.models.project import Project
from app.models.team_member import TeamMember
from app.models.report import TestReport
from app.models.scenario import Scenario
from app.models.scenario_report import ScenarioReport, ScenarioReportStep
from app.models.schedule import Schedule
from app.models.traffic_record import TrafficRecord
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


def db_delete(db: Session, project_id: int) -> Project | None:
    db_project = db.query(Project).filter(Project.id == project_id).first()
    if db_project is None:
        return None
    try:
        report_ids = db.query(ScenarioReport.id).filter(ScenarioReport.project_id == project_id)
        db.query(ScenarioReportStep).filter(ScenarioReportStep.report_id.in_(report_ids)).delete(synchronize_session=False)
        for model in (Case, Interface, Environment, Mock, PerfTask, TestReport, ScenarioReport, Scenario, Schedule, TrafficRecord):
            db.query(model).filter(model.project_id == project_id).delete(synchronize_session=False)
        db.delete(db_project)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return db_project
