from sqlalchemy import Column, String, Integer, DateTime, func
from app.database import Base

class Project(Base):
    __tablename__ = "project"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


