import uuid

from fastapi import Request
from sqlalchemy.engine import Connection

from app.api.accounts.service import lock_customer_account, move_money
from app.api.events.service import amount_band, record
from app.core.config import CASH_MAX_AMOUNT
from app.core.errors import AppError


def check_amount(amount: int, maximum: int) -> None:
    if amount <= 0:
        raise AppError(422, "invalid_amount", "금액은 1원 이상이어야 합니다")
    if amount > maximum:
        raise AppError(422, "amount_limit_exceeded", f"1회 최대 {maximum:,}원까지 가능합니다")


def cash(conn: Connection, request: Request, user_id: int, amount: int, kind: str) -> dict:
    """kind는 'deposit' 또는 'withdrawal'."""
    check_amount(amount, CASH_MAX_AMOUNT)
    account = lock_customer_account(conn, user_id)
    transaction_id = str(uuid.uuid4())
    delta = amount if kind == "deposit" else -amount
    balance = move_money(conn, account["id"], delta, kind, transaction_id)
    record(conn, request, kind, "success", "completed", {"amount_band": amount_band(amount)})
    return {"transaction_id": transaction_id, "balance": balance}
