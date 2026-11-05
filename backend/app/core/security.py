from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Response

from app.core.config import DEVICE_COOKIE_DAYS, SESSION_MAX_MINUTES, Settings

SESSION_COOKIE = "podobank_session"
DEVICE_COOKIE = "podobank_device"
_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """없는 계정도 같은 시간이 걸리도록 가짜 해시를 검증한다."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (InvalidHashError, VerificationError):
        return False


def set_cookie(response: Response, name: str, value: str, max_age: int, settings: Settings, path: str = "/") -> None:
    response.set_cookie(name, value, max_age=max_age, path=path, httponly=True, samesite="lax",
                        secure=settings.cookie_secure)


def clear_cookie(response: Response, name: str, settings: Settings, path: str = "/") -> None:
    response.delete_cookie(name, path=path, httponly=True, samesite="lax", secure=settings.cookie_secure)


def set_login_cookies(response: Response, token: str, device_id: str, settings: Settings) -> None:
    """세션 쿠키(최대 60분)와 기기 쿠키(1년). 세션이 실제로 끝나는 시점은 서버가 정한다."""
    set_cookie(response, SESSION_COOKIE, token, SESSION_MAX_MINUTES * 60, settings)
    set_cookie(response, DEVICE_COOKIE, device_id, DEVICE_COOKIE_DAYS * 24 * 3600, settings)
