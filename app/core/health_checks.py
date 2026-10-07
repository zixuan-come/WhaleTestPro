from sqlalchemy import text


def database_is_ready(database_engine) -> bool:
    """Return whether a database engine can execute a minimal query."""
    try:
        with database_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True


def redis_is_ready(client) -> bool:
    """Return whether Redis accepts commands required by auth and RedBeat."""
    try:
        return bool(client.ping())
    except Exception:
        return False


def celery_broker_is_ready(celery_application) -> bool:
    """Open and immediately close a broker connection without publishing work."""
    try:
        with celery_application.connection_for_write(connect_timeout=1) as connection:
            connection.ensure_connection(max_retries=0)
    except Exception:
        return False
    return True
