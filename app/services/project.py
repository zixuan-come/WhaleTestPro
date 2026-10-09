from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.team_member import TeamMember, TeamRole
from app.models.schedule import Schedule
from app.repositories import project as project_repo
from app.services import schedule as schedule_service
from app.schemas.project import ProjectCreate, ProjectUpdate


def s_create(db: Session, project: ProjectCreate, owner_id: int):
    membership = (
        db.query(TeamMember)
        .filter(
            TeamMember.team_id == project.team_id,
            TeamMember.user_id == owner_id,
        )
        .first()
    )
    if membership is None or membership.role not in (
        TeamRole.OWNER.value,
        TeamRole.ADMIN.value,
    ):
        raise HTTPException(status_code=403, detail="只能在自己管理的团队中创建项目")
    return project_repo.db_create(db, project)


def s_get(db: Session, project_id: int, user_id: int):
    return project_repo.db_get_for_user(db, project_id, user_id)


def s_list(db: Session, user_id: int, team_id: int | None = None):
    return project_repo.db_list_for_user(db, user_id, team_id)


def s_update(db: Session, project_id: int, project: ProjectUpdate):
    return project_repo.db_update(db, project_id, project)


def s_delete(db: Session, project_id: int):
    schedule_ids = [
        schedule_id
        for (schedule_id,) in (
            db.query(Schedule.id)
            .filter(Schedule.project_id == project_id)
            .all()
        )
    ]
    deleted = project_repo.db_delete(db, project_id)
    for schedule_id in schedule_ids:
        schedule_service.process_sync_event(db, schedule_id)
    return deleted


def s_move_team(db: Session, project_id: int, target_team_id: int, user_id: int):
    project = project_repo.db_get(db, project_id)
    if project is None:
        raise HTTPException(404, "项目不存在")
    target_owner = (
        db.query(TeamMember)
        .filter(
            TeamMember.team_id == target_team_id,
            TeamMember.user_id == user_id,
            TeamMember.role == TeamRole.OWNER.value,
        )
        .first()
    )
    if target_owner is None:
        raise HTTPException(403, "只有目标团队所有者可以迁移项目")

    project.team_id = target_team_id
    db.commit()
    db.refresh(project)
    return project
