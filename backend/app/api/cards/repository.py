from sqlalchemy import text
from sqlalchemy.engine import Connection


def find_card_by_user(conn: Connection, user_id: int):
    return conn.execute(
        text("SELECT c.id, c.card_number FROM cards c JOIN accounts a ON a.id = c.account_id WHERE a.user_id = :u"),
        {"u": user_id},
    ).mappings().first()


def list_merchants(conn: Connection):
    return conn.execute(text("SELECT id, name, category, region FROM merchants ORDER BY id")).mappings().all()


def find_merchant(conn: Connection, merchant_id: int):
    return conn.execute(
        text("SELECT id, name, category, region, lat, lng FROM merchants WHERE id = :id"), {"id": merchant_id}
    ).mappings().first()


def insert_payment(conn: Connection, card_id: int, merchant_id: int, transaction_id: str, amount: int) -> None:
    conn.execute(
        text("INSERT INTO card_payments (card_id, merchant_id, transaction_id, amount) VALUES (:c, :m, :t, :a)"),
        {"c": card_id, "m": merchant_id, "t": transaction_id, "a": amount},
    )
