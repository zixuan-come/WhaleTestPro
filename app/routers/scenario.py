from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.scenario import ScenarioCreate, ScenarioOut
from app.services import scenario as scenario_service
from app.core.deps import get_current_user, get_current_project
from app.models.user import User
from app.models.project import Project


router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("", response_model=list[ScenarioOut])
def list_scenarios(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_project: Project = Depends(get_current_project),
):
    return scenario_service.s_list(db, current_project.id)


@router.post("", response_model=ScenarioOut, status_code=201)
def create_scenario(
    sc: ScenarioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_project: Project = Depends(get_current_project),
):
    return scenario_service.s_create(db, sc, current_project.id)


@router.get("/{scenario_id}", response_model=ScenarioOut)
def get_scenario(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_project: Project = Depends(get_current_project),
):
    sc = scenario_service.s_get(db, scenario_id, current_project.id)
    if sc is None:
        raise HTTPException(status_code=404, detail=f"场景 id={scenario_id} 不存在")
    return sc


@router.put("/{scenario_id}", response_model=ScenarioOut)
def update_scenario(
    scenario_id: int,
    patch: ScenarioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_project: Project = Depends(get_current_project),
):
    sc = scenario_service.s_update(db, scenario_id, current_project.id, patch)
    if sc is None:
        raise HTTPException(status_code=404, detail=f"场景 id={scenario_id} 不存在")
    return sc


@router.delete("/{scenario_id}", response_model=ScenarioOut)
def delete_scenario(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_project: Project = Depends(get_current_project),
):
    sc = scenario_service.s_delete(db, scenario_id, current_project.id)
    if sc is None:
        raise HTTPException(status_code=404, detail=f"场景 id={scenario_id} 不存在")
    return sc


@router.post("/{scenario_id}/run")
def run_scenario(
    scenario_id: int,
    env_id: int | None = None,   # query param,可选
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_project: Project = Depends(get_current_project),
):
    result = scenario_service.s_run(db, scenario_id, env_id, current_project.id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"场景 id={scenario_id} 不存在")
    return result
