import secrets
from dataclasses import dataclass

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.api.events.service import EventSink, record, transaction
from app.api.users import repository
from app.core.errors import AppError
from app.core.security import hash_password

NUMBER_RETRIES = 3


@dataclass(frozen=True)
class SignupData:
    phone_number: str
    password: str
    birth_year: int
    gender: str
    marital_status: str
    is_employed: bool


@dataclass(frozen=True)
class _Stored:
    phone_number: str
    password_hash: str
    birth_year: int
    gender: str
    marital_status: str
    is_employed: bool


def _account_number() -> str:
    digits = f"{secrets.randbelow(10**8):08d}"
    return f"100-{digits[:4]}-{digits[4:]}"


def _card_number() -> str:
    return "9410" + f"{secrets.randbelow(10**12):012d}"


def signup(engine: Engine, sink: EventSink, request, subject: str | None, name: str, data: SignupData) -> int:
    """사용자, 계좌, 체크카드를 한 트랜잭션으로 만든다.

    subject가 있으면 카카오 가입이고, 같은 카카오 계정이 이미 있으면 그 사용자를 돌려준다.
    subject가 없으면 자체 가입(이름 직접 입력)이다.
    """
    method = "kakao" if subject else "password"
    stored = _Stored(data.phone_number, hash_password(data.password), data.birth_year, data.gender,
                     data.marital_status, data.is_employed)
    for attempt in range(NUMBER_RETRIES):
        try:
            with transaction(engine, sink) as conn:
                user_id = repository.insert_user(conn, subject, name, stored)
                account_id = repository.insert_account(conn, user_id, _account_number())
                repository.insert_card(conn, account_id, _card_number())
                record(conn, request, "signup", "success", "completed", {"method": method})
                return user_id
        except IntegrityError as exc:
            message = str(exc.orig)
            if subject:
                with engine.connect() as conn:
                    existing = repository.find_id_by_subject(conn, subject)
                if existing is not None:
                    return existing
            if "uq_users_phone_number" in message:
                with transaction(engine, sink) as conn:
                    record(conn, request, "signup", "failure", "phone_already_registered", {"method": method})
                raise AppError(409, "phone_already_registered", "이미 가입된 전화번호입니다") from exc
            if attempt == NUMBER_RETRIES - 1:
                raise
    raise RuntimeError("unreachable")
