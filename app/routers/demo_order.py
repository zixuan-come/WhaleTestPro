from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.demo_order import DemoOrderCreate, DemoOrderOut
from app.services import demo_order as order_service

router = APIRouter(prefix="/demo/orders", tags=["demo"])


@router.post("", response_model=DemoOrderOut)
def create_order(order: DemoOrderCreate, db: Session = Depends(get_db)):
    return order_service.s_create(db, order)


@router.get("", response_model=list[DemoOrderOut])
def list_orders(db: Session = Depends(get_db)):
    return order_service.s_list(db)



