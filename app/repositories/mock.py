from sqlalchemy.orm import Session
from app.models.mock import Mock


def db_create(db: Session, mock, project_id: int):
    db_mock = Mock(**mock.model_dump(), project_id=project_id)
    db.add(db_mock)
    db.commit()
    db.refresh(db_mock)
    return db_mock


def db_get(db: Session, mock_id: int, project_id: int):
    return db.query(Mock).filter(
        Mock.id == mock_id,
        Mock.project_id == project_id,
    ).first()


def db_list(db: Session, project_id: int):
    return db.query(Mock).filter(Mock.project_id == project_id).all()


def db_update(db: Session, mock_id: int, mock, project_id: int):
    db_mock = db.query(Mock).filter(
        Mock.id == mock_id,
        Mock.project_id == project_id,
    ).first()
    if db_mock is None:
        return None
    for key, value in mock.model_dump().items():
        setattr(db_mock, key, value)
    db.commit()
    db.refresh(db_mock)
    return db_mock


def db_delete(db: Session, mock_id: int, project_id: int):
    db_mock = db.query(Mock).filter(
        Mock.id == mock_id,
        Mock.project_id == project_id,
    ).first()
    if db_mock is None:
        return None
    db.delete(db_mock)
    db.commit()
    return db_mock


def db_match(db: Session, project_id: int, path: str, method: str):
    """先精确匹配，再按每段 {参数} 做单段路径通配。"""
    normalized_path = "/" + path.lstrip("/")
    normalized_method = method.strip().upper()
    exact = db.query(Mock).filter(
        Mock.project_id == project_id,
        Mock.path == normalized_path,
        Mock.method == normalized_method,
    ).first()
    if exact is not None:
        return exact

    candidates = db.query(Mock).filter(
        Mock.project_id == project_id,
        Mock.method == normalized_method,
    ).all()
    actual_parts = normalized_path.strip("/").split("/")
    for candidate in candidates:
        pattern_parts = candidate.path.strip("/").split("/")
        if len(pattern_parts) != len(actual_parts):
            continue
        if all(
            part == actual or (part.startswith("{") and part.endswith("}") and len(part) > 2)
            for part, actual in zip(pattern_parts, actual_parts)
        ):
            return candidate
    return None
