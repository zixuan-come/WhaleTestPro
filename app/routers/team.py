from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.deps import get_current_team_admin_or_owner, get_current_team_member, get_current_user
from app.database import get_db
from app.models.team_member import TeamMember
from app.models.user import User
from app.schemas.response import ApiResponse, success_response
from app.schemas.team import TeamCreate, TeamOut
from app.schemas.team_member import TeamMemberCreate, TeamMemberOut, TeamMemberRoleUpdate
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
