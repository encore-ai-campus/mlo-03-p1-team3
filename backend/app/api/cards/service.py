import uuid

from fastapi import Request
from sqlalchemy.engine import Connection, Engine

from app.api.accounts.service import lock_customer_account, move_money
from app.api.cards import repository
from app.api.events.service import amount_band, record
from app.api.transactions.service import check_amount
from app.core.config import CASH_MAX_AMOUNT
from app.core.errors import AppError


def card_not_found() -> AppError:
    return AppError(404, "card_not_found", "카드를 찾을 수 없습니다")


def my_card(engine: Engine, user_id: int) -> dict:
    with engine.connect() as conn:
        card = repository.find_card_by_user(conn, user_id)
    if card is None:
        raise card_not_found()
    return {"card_last4": card["card_number"][-4:]}


def merchants(engine: Engine):
    with engine.connect() as conn:
        return repository.list_merchants(conn)


def pay(conn: Connection, request: Request, user_id: int, merchant_id: int, amount: int) -> dict:
    check_amount(amount, CASH_MAX_AMOUNT)
    merchant = repository.find_merchant(conn, merchant_id)
    if merchant is None:
        raise AppError(404, "merchant_not_found", "가맹점을 찾을 수 없습니다")
    account = lock_customer_account(conn, user_id)
    card = repository.find_card_by_user(conn, user_id)
    if card is None:
        raise card_not_found()

    transaction_id = str(uuid.uuid4())
    balance = move_money(conn, account["id"], -amount, "card_payment", transaction_id)
    repository.insert_payment(conn, card["id"], merchant["id"], transaction_id, amount)
    record(conn, request, "card_payment", "success", "completed",
           {"amount_band": amount_band(amount), "region": merchant["region"], "merchant_category": merchant["category"]})
    record(conn, request, "card_payment_location", "success", "completed",
           {"region": merchant["region"], "lat": float(merchant["lat"]), "lng": float(merchant["lng"]),
            "merchant_category": merchant["category"]},
           collection="card_payment_locations")
    return {"transaction_id": transaction_id, "balance": balance}
