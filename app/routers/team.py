from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.deps import get_current_team_admin_or_owner, get_current_team_member, get_current_user
from app.database import get_db
from app.models.team_member import TeamMember
from app.models.user import User
from app.schemas.response import ApiResponse, success_response
from app.schemas.team import TeamCreate, TeamOut, TeamUpdate, TeamTransfer, TeamPermissionUpdate, TeamPermissionOut
from app.schemas.team_member import TeamMemberCreate, TeamMemberOut, TeamMemberRoleUpdate
from app.schemas.team_invitation import TeamInvitationCreate, TeamInvitationOut
from app.schemas.user import UserOut
from app.services import team as team_service

router = APIRouter(prefix="/teams", tags=["teams"])

@router.get("", response_model=ApiResponse[list[TeamOut]])
def list_teams(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return success_response(team_service.s_list(db, current_user.id), message="查询成功")

@router.post("", response_model=ApiResponse[TeamOut], status_code=status.HTTP_201_CREATED)
def create_team(data: TeamCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try: result = team_service.s_create(db, data, current_user.id)
    except IntegrityError:
        db.rollback(); raise HTTPException(409, f"团队名 '{data.name}' 已存在")
    return success_response(result, message="团队创建成功", status_code=201)

@router.patch("/{team_id}", response_model=ApiResponse[TeamOut])
def update_team(team_id: int, data: TeamUpdate, db: Session = Depends(get_db), membership: TeamMember = Depends(get_current_team_admin_or_owner)):
    try: result = team_service.s_update_team(db, membership.team_id, data)
    except IntegrityError:
        db.rollback(); raise HTTPException(409, "团队名称已存在")
    return success_response(result, message="团队信息更新成功")

@router.post("/{team_id}/transfer", response_model=ApiResponse[TeamOut])
def transfer_team(team_id: int, data: TeamTransfer, db: Session = Depends(get_db), membership: TeamMember = Depends(get_current_team_admin_or_owner)):
    if membership.role != "owner": raise HTTPException(403, "只有团队所有者可以转让所有权")
    return success_response(team_service.s_transfer_owner(db, membership.team_id, data.user_id), message="团队所有权转让成功")

@router.post("/{team_id}/leave", response_model=ApiResponse[None])
def leave_team(team_id: int, db: Session = Depends(get_db), membership: TeamMember = Depends(get_current_team_member)):
    team_service.s_leave(db, membership.team_id, membership.user_id)
    return success_response(data=None, message="已退出团队")

@router.delete("/{team_id}", response_model=ApiResponse[None])
def delete_team(team_id: int, db: Session = Depends(get_db), membership: TeamMember = Depends(get_current_team_admin_or_owner)):
    if membership.role != "owner": raise HTTPException(403, "只有团队所有者可以删除团队")
    team_service.s_delete_team(db, membership.team_id)
    return success_response(data=None, message="团队已删除")
@router.get("/{team_id}/members", response_model=ApiResponse[list[TeamMemberOut]])
def list_members(team_id: int, db: Session = Depends(get_db), membership: TeamMember = Depends(get_current_team_member)):
    return success_response(team_service.s_list_members(db, membership.team_id), message="查询成功")

@router.get("/{team_id}/member-candidates", response_model=ApiResponse[list[UserOut]])
def candidates(team_id: int, keyword: str = Query(..., min_length=2, max_length=50), limit: int = Query(20, ge=1, le=50), db: Session = Depends(get_db), membership: TeamMember = Depends(get_current_team_admin_or_owner)):
    return success_response(team_service.s_candidates(db, membership.team_id, keyword, limit), message="查询成功")

@router.post("/{team_id}/members", response_model=ApiResponse[TeamMemberOut], status_code=201)
def add_member(team_id: int, data: TeamMemberCreate, db: Session = Depends(get_db), membership: TeamMember = Depends(get_current_team_admin_or_owner)):
    return success_response(team_service.s_add(db, membership.team_id, data), message="成员添加成功", status_code=201)

@router.patch("/{team_id}/members/{member_id}", response_model=ApiResponse[TeamMemberOut])
def update_role(team_id: int, member_id: int, data: TeamMemberRoleUpdate, db: Session = Depends(get_db), membership: TeamMember = Depends(get_current_team_admin_or_owner)):
    return success_response(team_service.s_update_role(db, membership.team_id, member_id, data.role), message="成员角色更新成功")

@router.delete("/{team_id}/members/{member_id}", response_model=ApiResponse[None])
def remove_member(team_id: int, member_id: int, db: Session = Depends(get_db), membership: TeamMember = Depends(get_current_team_admin_or_owner)):
    team_service.s_remove(db, membership.team_id, member_id)
    return success_response(data=None, message="成员移除成功")

@router.post("/{team_id}/invitations", response_model=ApiResponse[TeamInvitationOut], status_code=201)
def invite_member(team_id: int, data: TeamInvitationCreate, db: Session = Depends(get_db), membership: TeamMember = Depends(get_current_team_admin_or_owner)):
    return success_response(team_service.s_invite(db, membership.team_id, membership.user_id, data.user_id, data.role), message="邀请已发送", status_code=201)

@router.get("/invitations", response_model=ApiResponse[list[TeamInvitationOut]])
def list_invitations(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return success_response(team_service.s_list_invitations(db, current_user.id), message="查询成功")

@router.post("/invitations/{invitation_id}/respond", response_model=ApiResponse[TeamInvitationOut])
def respond_invitation(invitation_id: int, accept: bool, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return success_response(team_service.s_respond_invitation(db, invitation_id, current_user.id, accept), message="邀请处理成功")
@router.get("/{team_id}/permissions", response_model=ApiResponse[list[TeamPermissionOut]])
def list_permissions(team_id: int, db: Session = Depends(get_db), membership: TeamMember = Depends(get_current_team_member)):
    return success_response(team_service.s_list_permissions(db, membership.team_id), message="查询成功")

@router.put("/{team_id}/permissions", response_model=ApiResponse[TeamPermissionOut])
def set_permission(team_id: int, data: TeamPermissionUpdate, db: Session = Depends(get_db), membership: TeamMember = Depends(get_current_team_admin_or_owner)):
    return success_response(team_service.s_set_permission(db, membership.team_id, data.role, data.permission, data.enabled), message="权限配置已更新")