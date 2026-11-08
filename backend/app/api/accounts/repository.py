from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.config import LOCK_WAIT_SECONDS


def find_by_user(conn: Connection, user_id: int):
    return conn.execute(
        text("SELECT id, account_number, balance FROM accounts WHERE user_id = :u"), {"u": user_id}
    ).mappings().first()


def find_by_number(conn: Connection, account_number: str):
    return conn.execute(
        text("SELECT a.id, a.account_number, a.user_id, u.name FROM accounts a JOIN users u ON u.id = a.user_id"
             " WHERE a.account_number = :n AND u.role = 'customer'"), {"n": account_number}
    ).mappings().first()


def find_by_phone(conn: Connection, phone: str):
    return conn.execute(
        text("SELECT a.id, a.account_number, a.user_id, u.name FROM accounts a JOIN users u ON u.id = a.user_id"
             " WHERE u.phone_number = :p AND u.role = 'customer'"), {"p": phone}
    ).mappings().first()


def lock(conn: Connection, account_id: int):
    return conn.execute(
        text(f"SELECT id, user_id, balance FROM accounts WHERE id = :id FOR UPDATE WAIT {LOCK_WAIT_SECONDS}"),
        {"id": account_id},
    ).mappings().first()


def lock_by_user(conn: Connection, user_id: int):
    return conn.execute(
        text(f"SELECT id, user_id, balance FROM accounts WHERE user_id = :u FOR UPDATE WAIT {LOCK_WAIT_SECONDS}"),
        {"u": user_id},
    ).mappings().first()


def add_balance(conn: Connection, account_id: int, delta: int) -> bool:
    """잔액이 음수가 되면 바꾸지 않고 False를 돌려준다."""
    result = conn.execute(
        text("UPDATE accounts SET balance = balance + :d WHERE id = :id AND balance + :d >= 0"),
        {"d": delta, "id": account_id},
    )
    return result.rowcount == 1


def balance_of(conn: Connection, account_id: int) -> int:
    return conn.execute(text("SELECT balance FROM accounts WHERE id = :id"), {"id": account_id}).scalar_one()


def insert_ledger(conn: Connection, transaction_id: str, account_id: int, entry_type: str, amount: int,
                  balance_after: int) -> None:
    conn.execute(
        text("INSERT INTO ledger_entries (transaction_id, account_id, entry_type, amount, balance_after)"
             " VALUES (:t, :a, :e, :m, :b)"),
        {"t": transaction_id, "a": account_id, "e": entry_type, "m": amount, "b": balance_after},
    )


def list_ledger(conn: Connection, account_id: int, limit: int, offset: int):
    return conn.execute(
        text("SELECT transaction_id, entry_type, amount, balance_after, created_at FROM ledger_entries"
             " WHERE account_id = :a ORDER BY id DESC LIMIT :l OFFSET :o"),
        {"a": account_id, "l": limit, "o": offset},
    ).mappings().all()


def lock_pair(conn: Connection, a: int, b: int):
    return conn.execute(
        text("SELECT id, user_id, balance FROM accounts WHERE id IN (:a, :b) ORDER BY id"
             f" FOR UPDATE WAIT {LOCK_WAIT_SECONDS}"),
        {"a": a, "b": b},
    ).mappings().all()


def apply_transfer(conn: Connection, sender_id: int, receiver_id: int, amount: int) -> bool:
    result = conn.execute(
        text("UPDATE accounts SET balance = balance + CASE WHEN id = :s THEN :neg ELSE :pos END"
             " WHERE id IN (:s, :r)"
             " AND balance + CASE WHEN id = :s THEN :neg ELSE :pos END >= 0"),
        {"s": sender_id, "r": receiver_id, "neg": -amount, "pos": amount},
    )
    return result.rowcount == 2


def insert_transfer_ledger(conn: Connection, transaction_id: str, sender_id: int, receiver_id: int,
                           amount: int, sender_balance: int, receiver_balance: int) -> None:
    conn.execute(
        text("INSERT INTO ledger_entries (transaction_id, account_id, entry_type, amount, balance_after)"
             " VALUES (:t, :s, 'transfer_out', :neg, :sb), (:t, :r, 'transfer_in', :pos, :rb)"),
        {"t": transaction_id, "s": sender_id, "r": receiver_id, "neg": -amount, "pos": amount,
         "sb": sender_balance, "rb": receiver_balance},
    )
