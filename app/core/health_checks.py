from sqlalchemy import text


def database_is_ready(database_engine) -> bool:
    """Return whether a database engine can execute a minimal query."""
    try:
        with database_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
