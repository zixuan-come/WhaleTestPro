from sqlalchemy import Column, Integer, String, ForeignKey, JSON
from app.database import Base


class Case(Base):
    __tablename__ = "test_case"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    interface_id = Column(Integer, ForeignKey("interface.id"), nullable=False)
    expected_status = Column(Integer, nullable=False)
    extract_rules = Column(JSON, nullable=True)
    assertions = Column(JSON, nullable=True)
    setup_sql = Column(JSON, nullable=True)
    teardown_sql = Column(JSON, nullable=True)
    datasets = Column(JSON, nullable=True)
    retries = Column(Integer, default=0)
    tags = Column(JSON, nullable=True)








