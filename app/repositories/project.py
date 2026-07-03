from sqlalchemy.orm import Session
from app.models.project import Project
from app.schemas.project import ProjectCreate


def db_create(db: Session, project: ProjectCreate) -> Project:
    db_project = Project(**project.model_dump())
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project


def db_get(db: Session, project_id: int) -> Project | None:
    return db.query(Project).filter(Project.id == project_id).first()


def db_list(db: Session) -> list[Project]:
    # 按 created_at 倒序:刚建的项目排在最前面,顶部下拉体验更好
    return db.query(Project).order_by(Project.created_at.desc()).all()


def db_delete(db: Session, project_id: int) -> Project | None:
    db_project = db.query(Project).filter(Project.id == project_id).first()
    if db_project is None:
        return None
    db.delete(db_project)
    db.commit()
    return db_project
