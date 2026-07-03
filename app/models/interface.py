from sqlalchemy import Column, Integer, String, JSON, ForeignKey
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
    # 多项目:每条接口必须归属某个 project,期二迁移已把旧数据全塞到 id=1
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)









