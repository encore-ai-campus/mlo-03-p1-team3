from sqlalchemy.engine import Connection, Engine

from app.api.accounts import repository
from app.core.errors import AppError


def insufficient_funds() -> AppError:
    return AppError(409, "insufficient_funds", "잔액이 부족합니다")


def account_not_found() -> AppError:
    return AppError(404, "account_not_found", "계좌를 찾을 수 없습니다")


def move_money(conn: Connection, account_id: int, delta: int, entry_type: str, transaction_id: str) -> int:
    """잠근 계좌의 잔액을 바꾸고 원장 한 줄을 남긴다. 새 잔액을 돌려준다."""
    if not repository.add_balance(conn, account_id, delta):
        raise insufficient_funds()
    balance = repository.balance_of(conn, account_id)
    repository.insert_ledger(conn, transaction_id, account_id, entry_type, delta, balance)
    return balance


def lock_customer_account(conn: Connection, user_id: int):
    account = repository.lock_by_user(conn, user_id)
    if account is None:
        raise account_not_found()
    return account


def my_account(engine: Engine, user_id: int):
    with engine.connect() as conn:
        account = repository.find_by_user(conn, user_id)
    if account is None:
        raise account_not_found()
    return account


def my_ledger(engine: Engine, user_id: int, limit: int, offset: int):
    with engine.connect() as conn:
        account = repository.find_by_user(conn, user_id)
        if account is None:
            raise account_not_found()
        return repository.list_ledger(conn, account["id"], limit, offset)
