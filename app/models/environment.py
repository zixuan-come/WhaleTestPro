from sqlalchemy import Column, Integer, String, JSON
from app.database import Base

class Environment(Base):
    __tablename__ = "environment"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    base_url = Column(String(500), nullable=False)
    variables = Column(JSON, nullable=True)












