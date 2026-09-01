from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.team import Team
from app.models.team_member import TeamRole
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
    db.add(TeamMember(team_id=team_id, user_id=data.user_id, role=data.role)); db.commit()
    return team_repo.db_get_member_by_id(db, team_id, db.query(TeamMember).order_by(TeamMember.id.desc()).first().id)

def s_update_role(db: Session, team_id: int, member_id: int, role: str):
    membership=team_repo.db_get_member_by_id(db, team_id, member_id)
    if membership is None: raise HTTPException(404, "团队成员不存在")
    if membership.role == TeamRole.OWNER.value: raise HTTPException(409, "团队所有者角色不能修改")
    membership.role=role; db.commit(); db.refresh(membership); return membership

def s_remove(db: Session, team_id: int, member_id: int):
    membership=team_repo.db_get_member_by_id(db, team_id, member_id)
    if membership is None: raise HTTPException(404, "团队成员不存在")
    if membership.role == TeamRole.OWNER.value: raise HTTPException(409, "团队所有者不能被移除")
    db.delete(membership); db.commit()
