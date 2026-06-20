from sqlalchemy import Column, Integer, String, ForeignKey
from app.database import Base


class Case(Base):
    __tablename__ = "test_case"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    interface_id = Column(Integer, ForeignKey("interface.id"), nullable=False)
    expected_status = Column(Integer, nullable=False)








