from app.core.health_checks import database_is_ready


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
