from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.team import Team
from app.models.project import Project
from app.models.team_member import TeamMember
from app.models.team_member import TeamRole
from app.models.team_invitation import TeamInvitation
from app.models.team_permission import TeamPermission
from app.repositories import team as team_repo
from app.repositories import team_invitation as invitation_repo
from app.repositories import user as user_repo


def s_list(db: Session, user_id: int): return team_repo.db_list_for_user(db, user_id)

def s_create(db: Session, data, owner_id: int): return team_repo.db_create(db, Team(**data.model_dump()), owner_id)

def s_list_members(db: Session, team_id: int): return team_repo.db_list_members(db, team_id)

def s_candidates(db: Session, team_id: int, keyword: str, limit: int): return team_repo.db_candidates(db, team_id, keyword.strip(), limit)

def s_add(db: Session, team_id: int, data):
    if user_repo.db_get_by_id(db, data.user_id) is None: raise HTTPException(404, "用户不存在")
    if team_repo.db_get(db, team_id, data.user_id) is not None: raise HTTPException(409, "用户已经是团队成员")
    membership = TeamMember(team_id=team_id, user_id=data.user_id, role=data.role)
    db.add(membership)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "用户已经是团队成员")
    return team_repo.db_get_member_by_id(db, team_id, membership.id)


def _lock_team(db: Session, team_id: int) -> Team:
    team = (
        db.query(Team)
        .filter(Team.id == team_id)
        .with_for_update()
        .first()
    )
    if team is None:
        raise HTTPException(404, "团队不存在")
    return team


def s_update_role(db: Session, team_id: int, member_id: int, role: str):
    team = _lock_team(db, team_id)
    membership = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id, TeamMember.id == member_id)
        .with_for_update()
        .first()
    )
    if membership is None: raise HTTPException(404, "团队成员不存在")
    if membership.user_id == team.owner_id or membership.role == TeamRole.OWNER.value:
        raise HTTPException(409, "团队所有者角色不能修改")
    membership.role=role
    db.commit(); db.refresh(membership); return membership

def s_remove(db: Session, team_id: int, member_id: int):
    team = _lock_team(db, team_id)
    membership = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id, TeamMember.id == member_id)
        .with_for_update()
        .first()
    )
    if membership is None: raise HTTPException(404, "团队成员不存在")
    if membership.user_id == team.owner_id or membership.role == TeamRole.OWNER.value:
        raise HTTPException(409, "团队所有者不能被移除")
    db.delete(membership)
    db.commit()

def s_update_team(db: Session, team_id: int, data):
    team = db.query(Team).filter(Team.id == team_id).first()
    if team is None: raise HTTPException(404, '团队不存在')
    team.name = data.name
    team.description = data.description
    db.commit()
    db.refresh(team)
    return team

def s_delete_team(db: Session, team_id: int):
    team = db.query(Team).filter(Team.id == team_id).first()
    if team is None: raise HTTPException(404, '团队不存在')
    if db.query(Project).filter(Project.team_id == team_id).count(): raise HTTPException(409, '团队下仍有项目，无法删除')
    db.delete(team); db.commit()

def s_transfer_owner(
    db: Session,
    team_id: int,
    actor_user_id: int,
    target_user_id: int,
):
    # 锁住 Team 行，把同一团队的所有权转让串行化。依赖层的 membership
    # 可能是在等待锁之前读取的，因此拿到锁后必须再次验证当前 owner。
    team = _lock_team(db, team_id)
    if team.owner_id != actor_user_id:
        raise HTTPException(403, "只有当前团队所有者可以转让所有权")
    if target_user_id == actor_user_id:
        raise HTTPException(409, "不能将所有权转让给自己")

    memberships = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id)
        .with_for_update()
        .all()
    )
    target = next(
        (item for item in memberships if item.user_id == target_user_id),
        None,
    )
    if target is None:
        raise HTTPException(404, "目标成员不存在")

    current_owner = next(
        (item for item in memberships if item.user_id == actor_user_id),
        None,
    )
    if current_owner is None or current_owner.role != TeamRole.OWNER.value:
        raise HTTPException(409, "团队所有者成员关系异常，请先修复数据")

    # 同时修复历史上可能残留的多 owner：目标以外的 owner 全部降为 admin。
    for membership in memberships:
        if membership.role == TeamRole.OWNER.value and membership.user_id != target_user_id:
            membership.role = TeamRole.ADMIN.value
    target.role = TeamRole.OWNER.value
    team.owner_id = target_user_id
    db.commit()
    db.refresh(team)
    return team

def s_leave(db: Session, team_id: int, user_id: int):
    team = _lock_team(db, team_id)
    membership = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        .with_for_update()
        .first()
    )
    if membership is None: raise HTTPException(404, '你不是该团队成员')
    if membership.user_id == team.owner_id or membership.role == TeamRole.OWNER.value:
        raise HTTPException(409, '团队所有者不能直接退出，请先转让所有权')
    db.delete(membership)
    db.commit()

def s_invite(db: Session, team_id: int, inviter_id: int, user_id: int, role: str):
    if user_repo.db_get_by_id(db, user_id) is None: raise HTTPException(404, '用户不存在')
    if team_repo.db_get(db, team_id, user_id) is not None: raise HTTPException(409, '用户已经是团队成员')
    existing = db.query(TeamInvitation).filter(TeamInvitation.team_id == team_id, TeamInvitation.invitee_id == user_id, TeamInvitation.status == 'pending').first()
    if existing: raise HTTPException(409, '该用户已有待处理邀请')
    invite = TeamInvitation(team_id=team_id, inviter_id=inviter_id, invitee_id=user_id, role=role)
    db.add(invite)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '该用户已有待处理邀请') from None
    db.refresh(invite)
    return invite

def s_list_invitations(
    db: Session,
    user_id: int,
    *,
    page: int,
    page_size: int,
    invitation_status: str | None = None,
):
    items, total = invitation_repo.db_page_for_invitee(
        db,
        user_id,
        invitation_status=invitation_status,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
    }

def s_respond_invitation(db: Session, invitation_id: int, user_id: int, accept: bool):
    invite = (
        db.query(TeamInvitation)
        .filter(
            TeamInvitation.id == invitation_id,
            TeamInvitation.invitee_id == user_id,
        )
        .with_for_update()
        .first()
    )
    if invite is None:
        raise HTTPException(404, '邀请不存在')
    if invite.status != 'pending':
        raise HTTPException(409, '邀请已经处理')
    if accept:
        if team_repo.db_get(db, invite.team_id, user_id) is None:
            db.add(TeamMember(team_id=invite.team_id, user_id=user_id, role=invite.role))
        invite.status = 'accepted'
    else:
        invite.status = 'rejected'
    from datetime import datetime
    invite.responded_at = datetime.utcnow()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '邀请处理发生冲突，请重试') from None
    db.refresh(invite)
    return invite
def s_list_permissions(db: Session, team_id: int):
    return db.query(TeamPermission).filter(TeamPermission.team_id == team_id).order_by(TeamPermission.role, TeamPermission.permission).all()

def s_set_permission(db: Session, team_id: int, role: str, permission: str, enabled: bool):
    item = db.query(TeamPermission).filter(TeamPermission.team_id == team_id, TeamPermission.role == role, TeamPermission.permission == permission).first()
    if item is None:
        item = TeamPermission(team_id=team_id, role=role, permission=permission, enabled=enabled); db.add(item)
    else: item.enabled = enabled
    db.commit(); db.refresh(item); return item
