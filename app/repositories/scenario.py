from sqlalchemy.orm import Session
from app.models.scenario import Scenario


# 五层 CRUD 标准骨架:每个方法都带 project_id 走多租户过滤(IDOR 铁律)

def db_create(db: Session, sc, project_id: int):
    obj = Scenario(**sc.model_dump(), project_id=project_id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def db_get(db: Session, scenario_id: int, project_id: int):
    return db.query(Scenario).filter(
        Scenario.id == scenario_id,
        Scenario.project_id == project_id,
    ).first()


def db_list(db: Session, project_id: int):
    return db.query(Scenario).filter(
        Scenario.project_id == project_id,
    ).order_by(Scenario.created_at.desc()).all()


def db_update(db: Session, scenario_id: int, project_id: int, patch):
    obj = db.query(Scenario).filter(
        Scenario.id == scenario_id,
        Scenario.project_id == project_id,
    ).first()
    if obj is None:
        return None
    for k, v in patch.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


def db_delete(db: Session, scenario_id: int, project_id: int):
    obj = db.query(Scenario).filter(
        Scenario.id == scenario_id,
        Scenario.project_id == project_id,
    ).first()
    if obj is None:
        return None
    db.delete(obj)
    db.commit()
    return obj
