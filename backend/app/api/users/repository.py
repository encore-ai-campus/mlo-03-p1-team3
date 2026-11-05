from sqlalchemy import text
from sqlalchemy.engine import Connection


def insert_user(conn: Connection, subject: str | None, name: str, data) -> int:
    return conn.execute(
        text("INSERT INTO users (kakao_subject, phone_number, password_hash, name, birth_year, gender,"
             " marital_status, is_employed, role) VALUES (:s, :p, :h, :n, :b, :g, :m, :e, 'customer')"),
        {"s": subject, "p": data.phone_number, "h": data.password_hash, "n": name, "b": data.birth_year,
         "g": data.gender, "m": data.marital_status, "e": data.is_employed},
    ).lastrowid


def insert_account(conn: Connection, user_id: int, account_number: str) -> int:
    return conn.execute(
        text("INSERT INTO accounts (user_id, account_number) VALUES (:u, :a)"), {"u": user_id, "a": account_number}
    ).lastrowid


def insert_card(conn: Connection, account_id: int, card_number: str) -> None:
    conn.execute(text("INSERT INTO cards (account_id, card_number) VALUES (:a, :c)"), {"a": account_id, "c": card_number})



def find_id_by_subject(conn: Connection, subject: str) -> int | None:
    return conn.execute(text("SELECT id FROM users WHERE kakao_subject = :s"), {"s": subject}).scalar()
