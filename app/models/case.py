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
    # 冗余字段:能通过 interface_id JOIN interface 得到,但直接冗余更快、索引简单
    # 一致性由 service.s_create 保证:建 case 时校验 interface.project_id == case.project_id
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)








