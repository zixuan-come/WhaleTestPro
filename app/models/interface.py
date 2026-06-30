from sqlalchemy import Column, Integer, String, JSON
from app.database import Base


class Interface(Base):
    __tablename__ = "interface"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    method = Column(String(10), nullable=False)
    url = Column(String(500), nullable=False)
    headers = Column(JSON, nullable=True)
    params = Column(JSON, nullable=True)
    body = Column(JSON, nullable=True)









