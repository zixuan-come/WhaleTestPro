from app.core.migrations import run_all_migrations
from app.database import engine, engine_shadow


if __name__ == "__main__":
    run_all_migrations(engine, engine_shadow)
    print("数据库迁移完成：主库和影子库均已校验")
