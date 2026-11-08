import re
import uuid

from fastapi import Request
from sqlalchemy.engine import Connection, Engine

from app.api.accounts import repository as accounts
from app.api.accounts.service import account_not_found, insufficient_funds
from app.api.events.service import amount_band, record
from app.api.transactions.service import check_amount
from app.api.transfers import repository
from app.core.config import TRANSFER_DAILY_LIMIT, TRANSFER_MAX_AMOUNT
from app.core.errors import AppError
from app.core.time import kst_day_range, kst_now

ACCOUNT_NUMBER = re.compile(r"^\d{3}-\d{4}-\d{4}$")
PHONE = re.compile(r"^01\d{8,9}$")


def recipient_not_found() -> AppError:
    return AppError(404, "recipient_not_found", "받는 사람을 찾을 수 없습니다")


def find_recipient(conn: Connection, query: str):
    """전화번호(01로 시작, 하이픈 허용) 또는 계좌번호(000-0000-0000)로 고객 계좌를 찾는다.

    010-1234-5678은 계좌번호와 모양이 같으므로 전화번호인지 먼저 본다(계좌번호는 100-으로 시작).
    """
    query = query.strip()
    digits = query.replace("-", "")
    if PHONE.match(digits):
        return accounts.find_by_phone(conn, digits)
    if ACCOUNT_NUMBER.match(query):
        return accounts.find_by_number(conn, query)
    return None


def lookup(engine: Engine, query: str) -> dict:
    """받는 사람 확인용. 이름만 돌려주고 계좌번호는 돌려주지 않는다."""
    with engine.connect() as conn:
        return lookup_on(conn, query)


def lookup_on(conn: Connection, query: str) -> dict:
    row = find_recipient(conn, query)
    if row is None:
        raise recipient_not_found()
    return {"name": row["name"]}


def transfer(conn: Connection, request: Request, user_id: int, recipient: str, amount: int) -> dict:
    check_amount(amount, TRANSFER_MAX_AMOUNT)
    sender = accounts.find_by_user(conn, user_id)
    if sender is None:
        raise account_not_found()
    receiver = find_recipient(conn, recipient)
    if receiver is None:
        raise recipient_not_found()
    if receiver["id"] == sender["id"]:
        raise AppError(422, "self_transfer", "내 계좌로는 보낼 수 없습니다")

    # 교착을 막으려고 계좌 ID가 작은 쪽부터 잠근다.
    locked = {row["id"]: row for row in accounts.lock_pair(conn, *sorted((sender["id"], receiver["id"])))}
    if sender["id"] not in locked:
        raise account_not_found()
    if receiver["id"] not in locked:
        raise recipient_not_found()

    start, end = kst_day_range(kst_now())
    if repository.sent_between(conn, sender["id"], start, end) + amount > TRANSFER_DAILY_LIMIT:
        raise AppError(422, "daily_limit_exceeded", f"하루 송금 한도 {TRANSFER_DAILY_LIMIT:,}원을 넘습니다")

    sender_balance = locked[sender["id"]]["balance"]
    receiver_balance = locked[receiver["id"]]["balance"]
    if sender_balance < amount:
        raise insufficient_funds()
    if not accounts.apply_transfer(conn, sender["id"], receiver["id"], amount):
        raise insufficient_funds()

    transaction_id = str(uuid.uuid4())
    balance = sender_balance - amount
    accounts.insert_transfer_ledger(
        conn, transaction_id, sender["id"], receiver["id"], amount, balance, receiver_balance + amount,
    )
    record(conn, request, "transfer", "success", "completed", {"amount_band": amount_band(amount)})
    return {"transaction_id": transaction_id, "balance": balance}

