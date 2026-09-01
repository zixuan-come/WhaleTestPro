from sqlalchemy.orm import Session
from app.repositories import project as project_repo
from app.models.team_member import TeamMember, TeamRole
from app.schemas.project import ProjectCreate, ProjectUpdate


def s_create(db: Session, project: ProjectCreate, owner_id: int):
    if project.team_id is not None:
        membership = db.query(TeamMember).filter(TeamMember.team_id == project.team_id, TeamMember.user_id == owner_id).first()
        if membership is None or membership.role not in (TeamRole.OWNER.value, TeamRole.ADMIN.value):
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="只能在自己所属的团队中创建项目")
    return project_repo.db_create(db, project, owner_id)


def s_get(db: Session, project_id: int, user_id: int):
    return project_repo.db_get_for_user(db, project_id, user_id)


def s_list(db: Session, user_id: int):
    return project_repo.db_list_for_user(db, user_id)


def s_update(db: Session, project_id: int, project: ProjectUpdate):
    return project_repo.db_update(db, project_id, project)


def s_delete(db: Session, project_id: int):
    return project_repo.db_delete(db, project_id)
