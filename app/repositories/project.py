from sqlalchemy.orm import Session
from app.models.case import Case
from app.models.environment import Environment
from app.models.interface import Interface
from app.models.mock import Mock
from app.models.perf import PerfTask
from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectRole
from app.models.report import TestReport
from app.models.scenario import Scenario
from app.models.scenario_report import ScenarioReport, ScenarioReportStep
from app.models.schedule import Schedule
from app.models.traffic_record import TrafficRecord
from app.schemas.project import ProjectCreate


def db_create(db: Session, project: ProjectCreate, owner_id: int) -> Project:
    db_project = Project(**project.model_dump())
    db.add(db_project)

    db.flush()

    db_member = ProjectMember(
        project_id=db_project.id,
        user_id=owner_id,
        role=ProjectRole.OWNER.value,
    )
    db.add(db_member)

    db.commit()
    db.refresh(db_project)
    return db_project


def db_get(db: Session, project_id: int) -> Project | None:
    return db.query(Project).filter(Project.id == project_id).first()


def db_get_for_user(db: Session, project_id: int, user_id: int) -> Project | None:
    query = db.query(Project)
    query = query.join(ProjectMember, ProjectMember.project_id == Project.id)
    query = query.filter(Project.id == project_id, ProjectMember.user_id == user_id)
    return query.first()


def db_list(db: Session) -> list[Project]:
    # 按 created_at 倒序:刚建的项目排在最前面,顶部下拉体验更好
    return db.query(Project).order_by(Project.created_at.desc()).all()


def db_list_for_user(db: Session, user_id: int) -> list[Project]:
    query = db.query(Project)
    query = query.join(ProjectMember, ProjectMember.project_id == Project.id)
    query = query.filter(ProjectMember.user_id == user_id)
    return query.order_by(Project.created_at.desc()).all()


def db_update(db: Session, project_id: int, project) -> Project | None:
    db_project = db.query(Project).filter(Project.id == project_id).first()
    if db_project is None:
        return None

    for key, value in project.model_dump().items():
        setattr(db_project, key, value)

    db.commit()
    db.refresh(db_project)
    return db_project


def db_delete(db: Session, project_id: int) -> Project | None:
    db_project = db.query(Project).filter(Project.id == project_id).first()
    if db_project is None:
        return None

    try:
        report_ids = db.query(ScenarioReport.id).filter(
            ScenarioReport.project_id == project_id
        )
        db.query(ScenarioReportStep).filter(
            ScenarioReportStep.report_id.in_(report_ids)
        ).delete(synchronize_session=False)

        # Delete dependants before their parents; test cases reference interfaces.
        for model in (
            Case,
            Interface,
            Environment,
            Mock,
            PerfTask,
            TestReport,
            ScenarioReport,
            Scenario,
            Schedule,
            TrafficRecord,
            ProjectMember,
        ):
            db.query(model).filter(model.project_id == project_id).delete(
                synchronize_session=False
            )

        db.delete(db_project)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return db_project
