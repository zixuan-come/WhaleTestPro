from sqlalchemy import Column, Integer, String
from app.database import Base

class DemoOrder(Base):
    __tablename__ = "demo_orders"
    id = Column(Integer, primary_key=True, index=True)
    item = Column(String(100), nullable=False)









