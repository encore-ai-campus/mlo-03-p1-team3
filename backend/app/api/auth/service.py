import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import Request
from sqlalchemy.engine import Engine

from app.api.auth import repository
from app.api.auth.kakao import KakaoAuthError, KakaoUnavailableError
from app.api.events.service import record, transaction
from app.core.config import (
    KAKAO_SIGNUP_MINUTES,
    LOGIN_LOCK_MINUTES,
    LOGIN_MAX_FAILURES,
    SESSION_IDLE_MINUTES,
    SESSION_MAX_MINUTES,
    SESSION_TOUCH_SECONDS,
)
from app.core.errors import AppError
from app.core.security import verify_password
from app.core.time import kst_now
from app.observability.tracing import traced


def _invalid() -> AppError:
    return AppError(401, "invalid_credentials", "전화번호 또는 비밀번호가 올바르지 않습니다")


def _locked() -> AppError:
    return AppError(423, "account_locked", "비밀번호를 여러 번 틀려 잠시 잠겼습니다. 5분 후 다시 시도해 주세요")


def check_not_locked(conn, request: Request, user, method: str) -> None:
    now = kst_now()
    repository.reset_expired_lock(conn, user["id"], now)
    if user["locked_until"] is not None and user["locked_until"] > now:
        record(conn, request, "login", "failure", "account_locked", {"method": method})
        raise _locked()


@dataclass(frozen=True)
class ClientInfo:
    device_id: str
    client: str
    user_agent: str | None


def client_info(request: Request, device_cookie: str | None) -> "ClientInfo":
    return ClientInfo(normalize_device_id(device_cookie), normalize_client(request.headers.get("X-Client")),
                      request.headers.get("User-Agent"))


def login_with_password(engine: Engine, request: Request, phone: str, password: str, info: ClientInfo) -> str:
    """성공하면 세션을 만들고 쿠키에 넣을 값을 돌려준다."""
    with transaction(engine, request.app.state.events) as conn:
        user = repository.find_by_phone(conn, phone)
        if user is None:
            verify_password(None, password)
            record(conn, request, "login", "failure", "invalid_credentials", {"method": "password"})
            error = _invalid()
        else:
            try:
                check_not_locked(conn, request, user, "password")
            except AppError as exc:
                error = exc
            else:
                if verify_password(user["password_hash"], password):
                    # record_success가 사용자 행을 잠가서, 같은 기기 동시 로그인도 세션이 하나만 남는다.
                    repository.record_success(conn, user["id"])
                    token = start_session(conn, user["id"], info.device_id, info.client, info.user_agent, kst_now())
                    record(conn, request, "login", "success", "completed", {"method": "password"})
                    return token
                lock_until = kst_now() + timedelta(minutes=LOGIN_LOCK_MINUTES)
                repository.record_failure(conn, user["id"], LOGIN_MAX_FAILURES, lock_until)
                record(conn, request, "login", "failure", "invalid_credentials", {"method": "password"})
                error = _invalid()
    raise error


CLIENTS = frozenset({"web", "ios-app", "android-app"})
USER_AGENT_MAX = 255


@dataclass(frozen=True)
class SessionUser:
    id: int
    role: str
    name: str


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_client(value: str | None) -> str:
    """X-Client 헤더 값. 정해진 값이 아니면 web으로 본다."""
    return value if value in CLIENTS else "web"


def normalize_device_id(value: str | None) -> str:
    """기기 쿠키 값이 UUID가 아니면 새 기기 번호를 만든다."""
    try:
        return str(uuid.UUID(value or ""))
    except ValueError:
        return str(uuid.uuid4())


def start_session(conn, user_id: int, device_id: str, client: str, user_agent: str | None, now: datetime,
                  login_method: str = "password") -> str:
    """같은 기기의 살아 있는 세션은 끝내고 새 세션을 만든다. 쿠키에 넣을 원본 값을 돌려준다."""
    token = secrets.token_urlsafe(32)
    repository.end_device_sessions(conn, user_id, device_id, now)
    repository.insert_session(conn, hash_token(token), user_id, device_id, client,
                              user_agent[:USER_AGENT_MAX] if user_agent else None,
                              login_method, now)
    return token


def resolve_session(engine: Engine, token: str, now: datetime) -> SessionUser | None:
    with engine.begin() as conn:
        return resolve_session_on(conn, token, now)


@traced("auth.resolve_session")
def resolve_session_on(conn, token: str, now: datetime) -> SessionUser | None:
    """주어진 연결에서 세션을 확인한다. 커밋은 호출자가 담당한다."""
    row = repository.find_active_session(conn, hash_token(token))
    if row is None:
        return None
    if now - row["last_seen_at"] >= timedelta(minutes=SESSION_IDLE_MINUTES):
        repository.end_session(conn, row["id"], "idle_timeout", now)
        return None
    if now - row["created_at"] >= timedelta(minutes=SESSION_MAX_MINUTES):
        repository.end_session(conn, row["id"], "max_age", now)
        return None
    stale_before = now - timedelta(seconds=SESSION_TOUCH_SECONDS)
    if row["last_seen_at"] <= stale_before:
        repository.touch_session(conn, row["id"], now, stale_before)
    return SessionUser(id=row["user_id"], role=row["role"], name=row["name"])


def end_session(engine: Engine, token: str, now: datetime) -> None:
    """로그아웃. 없는 세션이나 이미 끝난 세션이면 아무 일도 하지 않는다."""
    with engine.begin() as conn:
        row = repository.find_active_session(conn, hash_token(token))
        if row is not None:
            repository.end_session(conn, row["id"], "logout", now)


@dataclass(frozen=True)
class KakaoResult:
    """authenticated면 token은 세션 값, registration_required면 임시 가입 값."""

    status: str
    token: str


def login_with_kakao(engine: Engine, request: Request, kakao, code: str, info: ClientInfo) -> KakaoResult:
    """카카오로 누구인지 확인한다. 우리 회원이면 세션을, 처음 온 사람이면 5분짜리 임시 가입을 만든다.

    카카오 토큰은 회원 번호를 받는 데만 쓰고 저장하지 않는다. 로그인 유지는 우리 세션으로만 한다.
    """
    try:
        profile = kakao.fetch_profile(code)
    except KakaoAuthError as exc:
        raise AppError(401, "kakao_authorization_failed", "카카오 로그인에 실패했습니다") from exc
    except KakaoUnavailableError as exc:
        raise AppError(503, "kakao_unavailable", "카카오 로그인을 잠시 사용할 수 없습니다") from exc

    now = kst_now()
    with transaction(engine, request.app.state.events) as conn:
        user = repository.find_by_kakao_subject(conn, profile.subject)
        if user is None:
            token = secrets.token_urlsafe(32)
            repository.insert_kakao_signup(conn, hash_token(token), profile.subject, profile.name, now,
                                           now + timedelta(minutes=KAKAO_SIGNUP_MINUTES))
            return KakaoResult("registration_required", token)
        if user["role"] != "customer":
            record(conn, request, "login", "failure", "invalid_credentials", {"method": "kakao"})
            error = _invalid()
        else:
            try:
                check_not_locked(conn, request, user, "kakao")
            except AppError as exc:
                error = exc
            else:
                token = start_session(conn, user["id"], info.device_id, info.client, info.user_agent, now, "kakao")
                record(conn, request, "login", "success", "completed", {"method": "kakao"})
                return KakaoResult("authenticated", token)
    raise error


def _signup_expired() -> AppError:
    return AppError(401, "signup_session_expired", "가입 시간이 지났습니다. 카카오 로그인을 다시 해 주세요")


def pending_kakao_signup(engine: Engine, token: str | None) -> tuple[str, str]:
    """임시 가입 값으로 (카카오 회원 번호, 이름)을 찾는다. 없거나 5분이 지났으면 401."""
    if not token:
        raise _signup_expired()
    with engine.connect() as conn:
        row = repository.find_kakao_signup(conn, hash_token(token), kst_now())
    if row is None:
        raise _signup_expired()
    return row["kakao_subject"], row["name"]


def finish_kakao_signup(engine: Engine, token: str, user_id: int, info: ClientInfo) -> str:
    """임시 가입을 지우고(다시 쓸 수 없게) 카카오 세션을 만든다."""
    with engine.begin() as conn:
        repository.delete_kakao_signup(conn, hash_token(token))
        return start_session(conn, user_id, info.device_id, info.client, info.user_agent, kst_now(), "kakao")
