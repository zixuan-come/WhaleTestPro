from sqlalchemy.orm import Session
from app.models.project import Project
from app.schemas.project import ProjectCreate
from app.models.project_member import ProjectMember, ProjectRole


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
    db.delete(db_project)
    db.commit()
    return db_project
