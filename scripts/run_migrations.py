from app.core.migrations import run_all_migrations
from app.database import engine, engine_shadow


def main():
    # run_all_migrations registers the complete ORM graph without importing
    # main.py, starting the API, or relying on test collection side effects.
    run_all_migrations(engine, engine_shadow)
    print("数据库迁移完成：主库和影子库均已校验")


if __name__ == "__main__":
    main()
