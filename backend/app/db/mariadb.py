import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.core.config import DB_MAX_OVERFLOW, DB_POOL_RECYCLE_SECONDS, DB_POOL_SIZE, DB_POOL_TIMEOUT_SECONDS


def make_engine(url: str) -> Engine:
    pool_size = int(os.environ.get("DB_POOL_SIZE", DB_POOL_SIZE))
    overflow = int(os.environ.get("DB_MAX_OVERFLOW", DB_MAX_OVERFLOW))
    timeout = int(os.environ.get("DB_POOL_TIMEOUT_SECONDS", DB_POOL_TIMEOUT_SECONDS))
    if not 1 <= pool_size <= 100 or not 0 <= overflow <= 100 or not 1 <= timeout <= 60:
        raise ValueError("Invalid database pool limits")
    connect_args = {"connect_timeout": 2, "charset": "utf8mb4",
                    "init_command": "SET time_zone = '+09:00', innodb_lock_wait_timeout = 3"}
    # Opt-in laboratory comparison only; normal deployment retains driver TLS behavior.
    if os.environ.get("DB_TLS_DISABLED", "false").lower() == "true":
        connect_args["ssl_disabled"] = True
    return create_engine(
        url,
        pool_size=pool_size,
        max_overflow=overflow,
        pool_timeout=timeout,
        # 연결을 꺼낼 때마다 ping 왕복을 보내지 않는다(160건/초에서 DB CPU 포화의 한 원인).
        # 대신 DB wait_timeout(28800초)보다 짧게 연결을 교체한다. DB 재시작 직후 끊긴 연결을 처음 쓴
        # 요청은 503이 될 수 있고, SQLAlchemy가 그 풀의 연결을 모두 무효화한 뒤 다시 연결한다.
        pool_pre_ping=os.environ.get("DB_POOL_PRE_PING", "false").lower() == "true",
        pool_recycle=DB_POOL_RECYCLE_SECONDS,
        # 잠금을 기다린 뒤 다른 트랜잭션이 커밋한 원장(1일 한도 합계 등)을 읽어야 한다.
        isolation_level="READ COMMITTED",
        connect_args=connect_args,
    )


LOCK_WAIT_TIMEOUT = 1205
DEADLOCK = 1213


def db_error_code(exc: Exception) -> int | None:
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", ())
    return args[0] if args and isinstance(args[0], int) else None


def to_app_error(exc: Exception):
    """잠금 대기 초과·교착은 409, 연결 실패·풀 대기 초과는 503 AppError로 바꾼다."""
    from app.core.errors import AppError

    if isinstance(exc, OperationalError) and db_error_code(exc) in (LOCK_WAIT_TIMEOUT, DEADLOCK):
        return AppError(409, "lock_timeout", "다른 거래를 처리하고 있습니다. 잠시 후 다시 시도해 주세요")
    if isinstance(exc, PoolTimeoutError):
        return AppError(503, "database_unavailable", "요청이 많아 잠시 처리할 수 없습니다")
    return AppError(503, "database_unavailable", "데이터베이스에 연결할 수 없습니다")


@contextmanager
def translate_db_errors():
    try:
        yield
    except (PoolTimeoutError, OperationalError) as exc:
        raise to_app_error(exc) from exc


def with_deadlock_retry(fn):
    """교착(1213)이면 한 번만 다시 시도한다."""
    try:
        return fn()
    except OperationalError as exc:
        if db_error_code(exc) != DEADLOCK:
            raise
    return fn()
