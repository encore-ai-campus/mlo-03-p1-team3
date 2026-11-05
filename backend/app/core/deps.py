from dataclasses import dataclass

from fastapi import Depends, Request

from app.api.auth.service import resolve_session
from app.core.errors import AppError
from app.core.security import SESSION_COOKIE
from app.core.time import utc_now


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
    user = resolve_session(request.app.state.engine, token, utc_now())
    if user is None:
        raise _unauthorized()
    return CurrentUser(id=user.id, role=user.role, name=user.name)


def require_customer(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if user.role != "customer":
        raise AppError(403, "forbidden", "고객만 사용할 수 있습니다")
    return user


def require_employee(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if user.role != "bank_employee":
        raise AppError(403, "forbidden", "은행 직원만 사용할 수 있습니다")
    return user
