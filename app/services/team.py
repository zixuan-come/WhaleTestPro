from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.team import Team
from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectRole
from app.models.team_member import TeamMember
from app.models.team_member import TeamRole
from app.models.team_invitation import TeamInvitation
from app.models.team_permission import TeamPermission
from app.repositories import team as team_repo
from app.repositories import user as user_repo


def s_list(db: Session, user_id: int): return team_repo.db_list_for_user(db, user_id)

def s_create(db: Session, data, owner_id: int): return team_repo.db_create(db, Team(**data.model_dump()), owner_id)

def s_list_members(db: Session, team_id: int): return team_repo.db_list_members(db, team_id)

def s_candidates(db: Session, team_id: int, keyword: str, limit: int): return team_repo.db_candidates(db, team_id, keyword.strip(), limit)

def s_add(db: Session, team_id: int, data):
    if user_repo.db_get_by_id(db, data.user_id) is None: raise HTTPException(404, "用户不存在")
    if team_repo.db_get(db, team_id, data.user_id) is not None: raise HTTPException(409, "用户已经是团队成员")
    from app.models.team_member import TeamMember
    membership = TeamMember(team_id=team_id, user_id=data.user_id, role=data.role)
    db.add(membership)
    for project in db.query(Project).filter(Project.team_id == team_id).all():
        if db.query(ProjectMember).filter(ProjectMember.project_id == project.id, ProjectMember.user_id == data.user_id).first() is None:
            db.add(ProjectMember(project_id=project.id, user_id=data.user_id, role=data.role))
    db.commit()
    return team_repo.db_get_member_by_id(db, team_id, membership.id)

def s_update_role(db: Session, team_id: int, member_id: int, role: str):
    membership=team_repo.db_get_member_by_id(db, team_id, member_id)
    if membership is None: raise HTTPException(404, "团队成员不存在")
    if membership.role == TeamRole.OWNER.value: raise HTTPException(409, "团队所有者角色不能修改")
    membership.role=role
    for project in db.query(Project).filter(Project.team_id == team_id).all():
        legacy = db.query(ProjectMember).filter(ProjectMember.project_id == project.id, ProjectMember.user_id == membership.user_id).first()
        if legacy: legacy.role = role
    db.commit(); db.refresh(membership); return membership

def s_remove(db: Session, team_id: int, member_id: int):
    membership=team_repo.db_get_member_by_id(db, team_id, member_id)
    if membership is None: raise HTTPException(404, "团队成员不存在")
    if membership.role == TeamRole.OWNER.value: raise HTTPException(409, "团队所有者不能被移除")
    db.delete(membership)
    db.query(ProjectMember).filter(ProjectMember.user_id == membership.user_id, ProjectMember.project_id.in_(db.query(Project.id).filter(Project.team_id == team_id))).delete(synchronize_session=False)
    db.commit()

def s_update_team(db: Session, team_id: int, data):
    team = db.query(Team).filter(Team.id == team_id).first()
    if team is None: raise HTTPException(404, '团队不存在')
    team.name = data.name; team.description = data.description; db.commit(); db.refresh(team); return team

def s_delete_team(db: Session, team_id: int):
    team = db.query(Team).filter(Team.id == team_id).first()
    if team is None: raise HTTPException(404, '团队不存在')
    if db.query(Project).filter(Project.team_id == team_id).count(): raise HTTPException(409, '团队下仍有项目，无法删除')
    db.delete(team); db.commit()

def s_transfer_owner(db: Session, team_id: int, user_id: int):
    team = db.query(Team).filter(Team.id == team_id).first()
    member = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id).first()
    if team is None or member is None: raise HTTPException(404, '目标成员不存在')
    old = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == team.owner_id).first()
    if old: old.role = TeamRole.ADMIN.value
    member.role = TeamRole.OWNER.value; team.owner_id = user_id
    for project in db.query(Project).filter(Project.team_id == team_id).all():
        old_pm = db.query(ProjectMember).filter(ProjectMember.project_id == project.id, ProjectMember.user_id == old.user_id).first() if old else None
        new_pm = db.query(ProjectMember).filter(ProjectMember.project_id == project.id, ProjectMember.user_id == user_id).first()
        if old_pm: old_pm.role = TeamRole.ADMIN.value
        if new_pm: new_pm.role = TeamRole.OWNER.value
        else: db.add(ProjectMember(project_id=project.id, user_id=user_id, role=ProjectRole.OWNER.value))
    db.commit(); db.refresh(team); return team

def s_leave(db: Session, team_id: int, user_id: int):
    membership = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id).first()
    if membership is None: raise HTTPException(404, '你不是该团队成员')
    if membership.role == TeamRole.OWNER.value: raise HTTPException(409, '团队所有者不能直接退出，请先转让所有权')
    db.delete(membership)
    db.query(ProjectMember).filter(ProjectMember.user_id == membership.user_id, ProjectMember.project_id.in_(db.query(Project.id).filter(Project.team_id == team_id))).delete(synchronize_session=False)
    db.commit()

def s_invite(db: Session, team_id: int, inviter_id: int, user_id: int, role: str):
    if user_repo.db_get_by_id(db, user_id) is None: raise HTTPException(404, '用户不存在')
    if team_repo.db_get(db, team_id, user_id) is not None: raise HTTPException(409, '用户已经是团队成员')
    existing = db.query(TeamInvitation).filter(TeamInvitation.team_id == team_id, TeamInvitation.invitee_id == user_id, TeamInvitation.status == 'pending').first()
    if existing: raise HTTPException(409, '该用户已有待处理邀请')
    invite = TeamInvitation(team_id=team_id, inviter_id=inviter_id, invitee_id=user_id, role=role)
    db.add(invite); db.commit(); db.refresh(invite); return invite

def s_list_invitations(db: Session, user_id: int):
    return db.query(TeamInvitation).filter(TeamInvitation.invitee_id == user_id).order_by(TeamInvitation.created_at.desc()).all()

def s_respond_invitation(db: Session, invitation_id: int, user_id: int, accept: bool):
    invite = db.query(TeamInvitation).filter(TeamInvitation.id == invitation_id, TeamInvitation.invitee_id == user_id, TeamInvitation.status == 'pending').first()
    if invite is None: raise HTTPException(404, '邀请不存在或已处理')
    if accept:
        if team_repo.db_get(db, invite.team_id, user_id) is None:
            db.add(TeamMember(team_id=invite.team_id, user_id=user_id, role=invite.role))
            for project in db.query(Project).filter(Project.team_id == invite.team_id).all():
                if db.query(ProjectMember).filter(ProjectMember.project_id == project.id, ProjectMember.user_id == user_id).first() is None:
                    db.add(ProjectMember(project_id=project.id, user_id=user_id, role=invite.role))
        invite.status = 'accepted'
    else:
        invite.status = 'rejected'
    from datetime import datetime
    invite.responded_at = datetime.utcnow(); db.commit(); db.refresh(invite); return invite
def s_list_permissions(db: Session, team_id: int):
    return db.query(TeamPermission).filter(TeamPermission.team_id == team_id).order_by(TeamPermission.role, TeamPermission.permission).all()

def s_set_permission(db: Session, team_id: int, role: str, permission: str, enabled: bool):
    item = db.query(TeamPermission).filter(TeamPermission.team_id == team_id, TeamPermission.role == role, TeamPermission.permission == permission).first()
    if item is None:
        item = TeamPermission(team_id=team_id, role=role, permission=permission, enabled=enabled); db.add(item)
    else: item.enabled = enabled
    db.commit(); db.refresh(item); return item