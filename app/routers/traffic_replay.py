from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.traffic_replay import ReplayRequest
from app.schemas.response import ApiResponse, success_response
from app.services import traffic_replay as traffic_replay_service
from app.core.deps import get_current_project
from app.models.project import Project

router = APIRouter(prefix="/traffic/replay", tags=["traffic"])


@router.post("/{record_id}", response_model=ApiResponse[dict])
def replay(
    record_id: int,
    req: ReplayRequest | None = None,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    req = req or ReplayRequest()
    result = traffic_replay_service.s_replay(
        db, record_id, current_project.id, req.env_id, req.field_rules
    )
    if result is None:
        raise HTTPException(status_code=404, detail="录制记录不存在")
    return success_response(result, message="流量回放完成")
