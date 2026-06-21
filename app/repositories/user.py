from app.models.user import User
from app.core.security import hash_password


def db_create(db, user):
    hashed = hash_password(user.password)
    db_user = User(username=user.username, hashed_password=hashed)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def db_get_by_username(db, username):
    return db.query(User).filter(User.username == username).first()


def db_get_by_id(db, user_id):
    return db.query(User).filter(User.id == user_id).first()



