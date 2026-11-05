import json

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.config import LOCK_WAIT_SECONDS

ACTIVE = ("pending", "repaying")


def _product(row) -> dict:
    product = dict(row)
    product["term_options"] = json.loads(product["term_options"])
    return product


def list_products(conn: Connection) -> list[dict]:
    rows = conn.execute(text("SELECT id, code, name, min_amount, max_amount, amount_step,"
                             " term_options FROM loan_products ORDER BY id")).mappings().all()
    return [_product(r) for r in rows]


def find_product(conn: Connection, code: str) -> dict | None:
    row = conn.execute(text("SELECT id, code, name, min_amount, max_amount, amount_step,"
                            " term_options FROM loan_products WHERE code = :c"), {"c": code}).mappings().first()
    return _product(row) if row else None


def has_active(conn: Connection, user_id: int) -> bool:
    return conn.execute(
        text("SELECT 1 FROM loan_applications WHERE user_id = :u AND status IN ('pending', 'repaying') LIMIT 1"),
        {"u": user_id},
    ).first() is not None


def insert_application(conn: Connection, user_id: int, product: dict, amount: int, term: int, installment: int) -> int:
    return conn.execute(
        text("INSERT INTO loan_applications (user_id, product_id, product_code, principal_amount,"
             " term_months, monthly_installment) VALUES (:u, :p, :c, :a, :t, :m)"),
        {"u": user_id, "p": product["id"], "c": product["code"], "a": amount, "t": term, "m": installment},
    ).lastrowid


def list_by_user(conn: Connection, user_id: int):
    return conn.execute(
        text("SELECT id, product_code, status, principal_amount, term_months, monthly_installment"
             " FROM loan_applications WHERE user_id = :u ORDER BY id DESC"), {"u": user_id}
    ).mappings().all()


def list_repayments(conn: Connection, application_id: int):
    return conn.execute(
        text("SELECT installment_number, due_date, amount, status"
             " FROM loan_repayments WHERE loan_application_id = :a ORDER BY installment_number"),
        {"a": application_id},
    ).mappings().all()


def list_pending(conn: Connection, limit: int):
    return conn.execute(
        text("SELECT a.id AS application_id, a.product_code, a.principal_amount AS amount,"
             " p.max_amount AS product_max_amount, a.term_months, u.is_employed FROM loan_applications a"
             " JOIN users u ON u.id = a.user_id JOIN loan_products p ON p.id = a.product_id"
             " WHERE a.status = 'pending' ORDER BY a.id LIMIT :l"), {"l": limit}
    ).mappings().all()


def lock_application(conn: Connection, application_id: int):
    return conn.execute(
        text("SELECT id, user_id, product_code, principal_amount, term_months, status"
             f" FROM loan_applications WHERE id = :i FOR UPDATE WAIT {LOCK_WAIT_SECONDS}"), {"i": application_id}
    ).mappings().first()


def insert_repayments(conn: Connection, application_id: int, rows: list[dict]) -> None:
    conn.execute(
        text("INSERT INTO loan_repayments (loan_application_id, installment_number, due_date, amount)"
             " VALUES (:a, :n, :d, :m)"),
        [{"a": application_id, **row} for row in rows],
    )


def mark_reviewed(conn: Connection, application_id: int, status: str, reviewer_id: int, now, approved: bool) -> None:
    conn.execute(
        text("UPDATE loan_applications SET status = :s, reviewed_by = :r, reviewed_at = :t,"
             " approved_at = IF(:ok, :t, NULL) WHERE id = :i"),
        {"s": status, "r": reviewer_id, "t": now, "ok": approved, "i": application_id},
    )


def due_application_ids(conn: Connection, as_of) -> list[int]:
    return list(conn.execute(
        text("SELECT DISTINCT r.loan_application_id FROM loan_repayments r"
             " JOIN loan_applications a ON a.id = r.loan_application_id"
             " WHERE r.status IN ('scheduled', 'overdue') AND r.due_date <= :d AND a.status = 'repaying'"
             " ORDER BY r.loan_application_id"), {"d": as_of}
    ).scalars())


def lock_installments(conn: Connection, application_id: int, statuses: tuple[str, ...], as_of):
    """as_of까지 기한이 된 회차를 오래된 것부터 잠근다."""
    params = {"a": application_id, "d": as_of, **{f"s{i}": s for i, s in enumerate(statuses)}}
    names = ", ".join(f":s{i}" for i in range(len(statuses)))
    return conn.execute(
        text(f"SELECT id, installment_number, amount, status FROM loan_repayments"
             f" WHERE loan_application_id = :a AND status IN ({names}) AND due_date <= :d"
             f" ORDER BY installment_number FOR UPDATE WAIT {LOCK_WAIT_SECONDS}"), params
    ).mappings().all()


def mark_installment(conn: Connection, installment_id: int, status: str, now) -> None:
    conn.execute(
        text("UPDATE loan_repayments SET status = :s, processed_at = :t,"
             " paid_at = IF(:s = 'paid', :t, paid_at) WHERE id = :i"),
        {"s": status, "t": now, "i": installment_id},
    )


def has_unpaid(conn: Connection, application_id: int) -> bool:
    return conn.execute(
        text("SELECT 1 FROM loan_repayments WHERE loan_application_id = :a AND status <> 'paid' LIMIT 1"),
        {"a": application_id},
    ).first() is not None


def set_status(conn: Connection, application_id: int, status: str) -> None:
    conn.execute(text("UPDATE loan_applications SET status = :s WHERE id = :i"), {"s": status, "i": application_id})
