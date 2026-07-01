from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from app.core.config import settings
from app.core.shadow_ctx import is_shadow

engine = create_engine(settings.DATABASE_URL)
engine_shadow = create_engine(settings.SHADOW_DATABASE_URL)
Base = declarative_base()

class RoutingSession(Session):
    def get_bind(self, mapper=None, clause=None, **kwargs):
        if is_shadow():
            return engine_shadow
        return engine


SessionLocal = sessionmaker(autocommit=False, autoflush=False, class_=RoutingSession)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()







