from sqlalchemy.orm import Session
from app.repositories import interface as api_repo


# Service 层纯转手,只是每个方法多带一个 project_id 参数,原样传给 repository。
# 期一 Interface Service 只有 db(转手 1 个参数),现在转手 2 个 —— 就多一个字。

def s_create(db: Session, interface, project_id: int):
    return api_repo.db_create(db, interface, project_id)


def s_get(db: Session, interface_id: int, project_id: int):
    return api_repo.db_get(db, interface_id, project_id)


def s_list(db: Session, project_id: int):
    return api_repo.db_list(db, project_id)


def s_delete(db: Session, interface_id: int, project_id: int):
    return api_repo.db_delete(db, interface_id, project_id)
