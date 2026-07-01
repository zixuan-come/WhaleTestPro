from app.models.mock import Mock


def db_create(db, mock):
    db_mock = Mock(**mock.model_dump())
    db.add(db_mock)
    db.commit()
    db.refresh(db_mock)
    return db_mock


def db_get(db, mock_id):
    return db.query(Mock).filter(Mock.id == mock_id).first()


def db_list(db):
    return db.query(Mock).all()


def db_update(db, mock_id, mock):
    db_mock = db.query(Mock).filter(Mock.id == mock_id).first()
    if db_mock is None:
        return None
    for key, value in mock.model_dump().items():
        setattr(db_mock, key, value)
    db.commit()
    db.refresh(db_mock)
    return db_mock


def db_delete(db, mock_id):
    db_mock = db.query(Mock).filter(Mock.id == mock_id).first()
    if db_mock is None:
        return None
    db.delete(db_mock)
    db.commit()
    return db_mock


def db_match(db, path, method):
    return db.query(Mock).filter(Mock.path == path, Mock.method == method).first()


