from app.core.health_checks import (
    celery_broker_is_ready,
    database_is_ready,
    redis_is_ready,
)


class _Connection:
    def __init__(self):
        self.executed = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, statement):
        self.executed = str(statement)


class _ReadyEngine:
    def __init__(self):
        self.connection = _Connection()

    def connect(self):
        return self.connection


class _UnavailableEngine:
    def connect(self):
        raise OSError("database unavailable")


def test_database_is_ready_executes_minimal_query():
    engine = _ReadyEngine()

    assert database_is_ready(engine) is True
    assert engine.connection.executed == "SELECT 1"


def test_database_is_ready_returns_false_when_connection_fails():
    assert database_is_ready(_UnavailableEngine()) is False


class _Redis:
    def __init__(self, error=None):
        self.error = error

    def ping(self):
        if self.error:
            raise self.error
        return True


class _BrokerConnection:
    def __init__(self, error=None):
        self.error = error
        self.max_retries = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def ensure_connection(self, max_retries):
        self.max_retries = max_retries
        if self.error:
            raise self.error


class _Celery:
    def __init__(self, connection):
        self.connection = connection

    def connection_for_write(self, **kwargs):
        self.connection.options = kwargs
        return self.connection


def test_redis_is_ready_checks_ping_and_handles_failure():
    assert redis_is_ready(_Redis()) is True
    assert redis_is_ready(_Redis(OSError("redis unavailable"))) is False


def test_celery_broker_is_ready_uses_non_retrying_connection():
    connection = _BrokerConnection()
    assert celery_broker_is_ready(_Celery(connection)) is True
    assert connection.max_retries == 0
    assert connection.options == {"connect_timeout": 1}
    assert celery_broker_is_ready(
        _Celery(_BrokerConnection(OSError("broker unavailable")))
    ) is False
