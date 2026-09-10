from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, func
from app.database import Base


class TestSuite(Base):
    __tablename__ = "test_suite"
    # 类名以 Test 开头，pytest 会误当测试类去收集并告警；显式声明非测试类
    __test__ = False

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    type = Column(String(20), nullable=False)  # 'scenario' / 'case' / 'mixed'

    # 配置
    scenario_ids = Column(JSON, nullable=True)  # [1, 2, 3]
    case_ids = Column(JSON, nullable=True)      # [10, 11, 12]
    tags = Column(JSON, nullable=True)          # ["smoke", "p0"]

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
