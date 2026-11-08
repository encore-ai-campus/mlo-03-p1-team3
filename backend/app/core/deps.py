from dataclasses import dataclass

from fastapi import Depends, Request

from app.api.auth.service import resolve_session, resolve_session_on
from app.core.errors import AppError
from app.core.security import SESSION_COOKIE
from app.core.time import kst_now


@dataclass(frozen=True)
class CurrentUser:
    id: int
    role: str
    name: str


def _unauthorized() -> AppError:
    return AppError(401, "authentication_required", "로그인이 필요합니다")


def current_user(request: Request) -> CurrentUser:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise _unauthorized()
    user = resolve_session(request.app.state.engine, token, kst_now())
    if user is None:
        raise _unauthorized()
    return CurrentUser(id=user.id, role=user.role, name=user.name)


async def require_customer(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if user.role != "customer":
        raise AppError(403, "forbidden", "고객만 사용할 수 있습니다")
    return user


def require_employee(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if user.role != "bank_employee":
        raise AppError(403, "forbidden", "은행 직원만 사용할 수 있습니다")
    return user


async def session_token(request: Request) -> str:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise _unauthorized()
    return token


def customer_on(conn, token: str) -> CurrentUser:
    user = resolve_session_on(conn, token, kst_now())
    if user is None:
        conn.commit()
        raise _unauthorized()
    if user.role != "customer":
        conn.commit()
        raise AppError(403, "forbidden", "고객만 사용할 수 있습니다")
    return CurrentUser(id=user.id, role=user.role, name=user.name)


def run_customer_read(request: Request, token: str, fn):
    with request.app.state.engine.connect() as conn:
        user = customer_on(conn, token)
        try:
            result = fn(conn, user)
        except AppError:
            conn.commit()
            raise
        conn.commit()
        return result


def run_customer(request: Request, token: str, fn):
    with request.app.state.engine.begin() as conn:
        user = customer_on(conn, token)
    return fn(user)
