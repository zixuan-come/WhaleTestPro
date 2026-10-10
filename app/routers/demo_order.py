from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.authorization import optional_project_for_recording
from app.schemas.demo_order import DemoOrderCreate, DemoOrderOut
from app.schemas.response import ApiResponse, success_response
from app.services import demo_order as order_service

router = APIRouter(prefix="/demo/orders", tags=["demo"], dependencies=[Depends(optional_project_for_recording)])


@router.post("", response_model=ApiResponse[DemoOrderOut], status_code=201)
def create_order(order: DemoOrderCreate, db: Session = Depends(get_db)):
    return success_response(
        order_service.s_create(db, order),
        message="订单创建成功",
        status_code=201,
    )


@router.get("", response_model=ApiResponse[list[DemoOrderOut]])
def list_orders(db: Session = Depends(get_db)):
    return success_response(order_service.s_list(db), message="查询成功")



