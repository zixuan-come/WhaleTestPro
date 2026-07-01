from sqlalchemy import Column, Integer, String, JSON
from app.database import Base


class Mock(Base):
    __tablename__ = "mock"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    path = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    status = Column(Integer, nullable=False, default=200)
    body = Column(JSON, nullable=True)
    delay_ms = Column(Integer, nullable=False, default=0)





