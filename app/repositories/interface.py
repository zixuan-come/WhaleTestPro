from app.models.interface import Interface


def db_create(db, interface):
    db_interface = Interface(**interface.model_dump())
    db.add(db_interface)
    db.commit()
    db.refresh(db_interface)
    return db_interface


def db_get(db, interface_id):
    return db.query(Interface).filter(Interface.id == interface_id).first()


def db_list(db):
    return db.query(Interface).all()


def db_delete(db, interface_id):
    db_interface = db.query(Interface).filter(Interface.id == interface_id).first()
    if db_interface is None:
        return None
    db.delete(db_interface)
    db.commit()
    return db_interface



