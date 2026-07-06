from sqlalchemy.orm import Session
from app.models.interface import Interface


# 每个方法都多带一个 project_id 参数,SQL 里全部 WHERE 加 project_id 过滤。
# 这是"多租户安全铁律":每次查询都在最底层锁租户 id,不指望上层记得校验。
# get/delete 不加过滤就是越权漏洞(你在 A 项目却读到 B 项目的接口)。

def db_create(db: Session, interface, project_id: int):
    # 建接口时,把当前项目 id 塞进 model 一起 add
    db_interface = Interface(**interface.model_dump(), project_id=project_id)
    db.add(db_interface)
    db.commit()
    db.refresh(db_interface)
    return db_interface


def db_get(db: Session, interface_id: int, project_id: int):
    # 双条件过滤:id + project_id 都匹配才返回,防越权
    return db.query(Interface).filter(
        Interface.id == interface_id,
        Interface.project_id == project_id,
    ).first()


def db_list(db: Session, project_id: int):
    # 列表只返回当前项目的接口
    return db.query(Interface).filter(Interface.project_id == project_id).all()


def db_delete(db: Session, interface_id: int, project_id: int):
    # 删除也要双条件,别项目的接口对当前用户表现为"不存在"
    db_interface = db.query(Interface).filter(
        Interface.id == interface_id,
        Interface.project_id == project_id,
    ).first()
    if db_interface is None:
        return None
    db.delete(db_interface)
    db.commit()
    return db_interface


def db_update(db:Session, interface_id: int, project_id: int, patch):
    db_interface = db.query(Interface).filter(
        Interface.id == interface_id,
        Interface.project_id == project_id,
    ).first()
    if db_interface is None:
        return None
    for k, v in patch.model_dump().items():
        setattr(db_interface, k, v)
    db.commit()
    db.refresh(db_interface)
    return db_interface


def db_rename_category(db: Session, project_id: int, old_name: str, new_name: str):
    # bulk UPDATE:一次 SQL 改所有匹配的接口,不循环查改
    count = db.query(Interface).filter(
        Interface.project_id == project_id,
        Interface.category == old_name,
    ).update({Interface.category: new_name})
    db.commit()
    return count


def db_delete_category(db: Session, project_id: int, name: str):
    # 删除分类 = 把所有引用的接口 category 置 NULL(接口本身不删)
    count = db.query(Interface).filter(
        Interface.project_id == project_id,
        Interface.category == name,
    ).update({Interface.category: None})
    db.commit()
    return count



