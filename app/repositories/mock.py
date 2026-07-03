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
    """
    挡板命中匹配:project_id 从 URL 前缀取(/mock/{pid}/xxx),不是从 header。
    因为调用方是被测系统/测试脚本,URL 里带 pid 是业界标准做法(Apifox/Postman Mock 同)。
    """
    return db.query(Mock).filter(
        Mock.project_id == project_id,
        Mock.path == path,
        Mock.method == method,
    ).first()
