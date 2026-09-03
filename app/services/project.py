from sqlalchemy.orm import Session
from app.repositories import project as project_repo
from app.models.team_member import TeamMember, TeamRole
from app.models.project_member import ProjectMember, ProjectRole
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


def s_list(db: Session, user_id: int, team_id: int | None = None):
    return project_repo.db_list_for_user(db, user_id, team_id)


def s_update(db: Session, project_id: int, project: ProjectUpdate):
    return project_repo.db_update(db, project_id, project)


def s_delete(db: Session, project_id: int):
    return project_repo.db_delete(db, project_id)

def s_move_team(db: Session, project_id: int, target_team_id: int, user_id: int):
    from fastapi import HTTPException
    from app.models.project import Project
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None: raise HTTPException(404, '项目不存在')
    target = db.query(TeamMember).filter(TeamMember.team_id == target_team_id, TeamMember.user_id == user_id).first()
    if target is None or target.role != TeamRole.OWNER.value: raise HTTPException(403, '只有目标团队所有者可以迁移项目')
    old_team_id = project.team_id
    project.team_id = target_team_id
    members = db.query(TeamMember).filter(TeamMember.team_id == target_team_id).all()
    for tm in members:
        pm = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == tm.user_id).first()
        role = ProjectRole.OWNER.value if tm.user_id == user_id else (ProjectRole.ADMIN.value if tm.role == TeamRole.ADMIN.value else ProjectRole.MEMBER.value)
        if pm: pm.role = role
        else: db.add(ProjectMember(project_id=project_id, user_id=tm.user_id, role=role))
    db.commit(); db.refresh(project); return project