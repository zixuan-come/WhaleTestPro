"""Fail-closed connection boundary for user-authored test SQL.

The configured account must have grants ONLY on the dedicated tested schema.
No fallback to SessionLocal (including the shadow platform database) is allowed.
"""
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import re

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import settings


@lru_cache(maxsize=4)
def _engine(url: str):
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "mysql":
        @event.listens_for(engine, "connect")
        def verify_account(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("SHOW GRANTS FOR CURRENT_USER")
                _validate_mysql_grants([row[0] for row in cursor.fetchall()], make_url(url).database)
            finally:
                cursor.close()
    return engine


def _validate_mysql_grants(grants, database):
    """Reject global, role, administrative and cross-schema privileges."""
    if not grants:
        raise ValueError("无法确认测试 SQL 账号权限，拒绝执行")
    for grant in grants:
        match = re.match(r"^GRANT (.+?) ON (.+?) TO ", grant, re.IGNORECASE)
        if not match or "WITH GRANT OPTION" in grant.upper():
            raise ValueError("测试 SQL 账号存在角色或管理权限，请仅授予测试库 DML 权限")
        privileges, target = match.groups()
        rights = {value.strip().upper() for value in privileges.split(",")}
        if rights == {"USAGE"} and target == "*.*":
            continue
        raw_schema = target.split(".", 1)[0].strip("`")
        # Database-level grants can contain wildcard patterns. Accept only
        # literal names, even when the configured database has the same spelling.
        literal_schema = []
        position = 0
        while position < len(raw_schema):
            character = raw_schema[position]
            if character == "\\":
                position += 1
                if position >= len(raw_schema) or raw_schema[position] not in {"_", "%", "\\"}:
                    raise ValueError("测试 SQL 账号授权库名存在不明确的转义，拒绝执行")
                character = raw_schema[position]
            elif character in {"_", "%"}:
                raise ValueError("测试 SQL 账号授权库名含未转义通配符，拒绝执行")
            literal_schema.append(character)
            position += 1
        schema = "".join(literal_schema)
        if schema != database or not rights <= {"SELECT", "INSERT", "UPDATE", "DELETE"}:
            raise ValueError("测试 SQL 账号权限超过独立测试库的 SELECT/INSERT/UPDATE/DELETE 范围")


def _validated_url() -> str:
    value = settings.TEST_DATABASE_URL
    if not value:
        raise ValueError("SQL 功能未启用，请配置独立且权限受限的 TEST_DATABASE_URL")
    tested = make_url(value)
    if tested.get_backend_name() == "mysql" and tested.username in {None, "root"}:
        raise ValueError("测试 SQL 禁止使用 root 或未指定账号")
    if tested.get_backend_name() == "sqlite" and (
        "uri" in tested.query or (tested.database or "").startswith("file:")
    ):
        raise ValueError("测试 SQL 不支持 SQLite URI 连接，请使用普通独立数据库文件")
    for platform_value in (settings.DATABASE_URL, settings.SHADOW_DATABASE_URL):
        platform = make_url(platform_value)
        if tested.get_backend_name() != platform.get_backend_name():
            continue
        if tested.get_backend_name() == "sqlite":
            if "uri" in platform.query or (platform.database or "").startswith("file:"):
                raise ValueError("平台使用 SQLite URI 时无法确认测试库隔离，拒绝执行")
            same_database = tested.database == platform.database
            if tested.database and platform.database and ":memory:" not in (tested.database, platform.database):
                same_database = Path(tested.database).resolve() == Path(platform.database).resolve()
        else:
            same_database = (
                tested.host, tested.port, tested.database
            ) == (platform.host, platform.port, platform.database)
            # A shared privileged account defeats schema isolation, even when
            # the URL points at a different database.
            if tested.username == platform.username:
                raise ValueError("测试 SQL 必须使用独立的受限数据库账号")
            # Reject same schema names regardless of hostname aliases/ports.
            same_database = same_database or tested.database == platform.database
        if same_database:
            raise ValueError("测试 SQL 禁止连接平台主库或影子库")
    return value


@contextmanager
def test_sql_session():
    with Session(_engine(_validated_url())) as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
