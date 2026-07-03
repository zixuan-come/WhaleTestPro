from sqlalchemy.orm import Session
from app.repositories import case as case_repo
from app.repositories import interface as interface_repo


def s_create(db: Session, case, project_id: int):
    # 一致性校验:case 关联的 interface 必须属于当前项目
    # 否则用户能在项目 A 建一个"关联项目 B 接口"的 case → 数据混乱
    interface = interface_repo.db_get(db, case.interface_id, project_id)
    if interface is None:
        # 返回 None,由 router 转成 400/404
        return None
    return case_repo.db_create(db, case, project_id)


def s_get(db: Session, case_id: int, project_id: int):
    return case_repo.db_get(db, case_id, project_id)


def s_list(db: Session, project_id: int):
    return case_repo.db_list(db, project_id)


def s_delete(db: Session, case_id: int, project_id: int):
    return case_repo.db_delete(db, case_id, project_id)
