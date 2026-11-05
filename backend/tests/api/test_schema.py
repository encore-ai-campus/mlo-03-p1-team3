import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.db.migrate import apply_migrations


def test_migrations_idempotent(engine):
    assert apply_migrations(engine) == []


def test_balance_cannot_be_negative(engine, make_user):
    user = make_user()
    with pytest.raises((IntegrityError, OperationalError)), engine.begin() as conn:
        conn.execute(text("UPDATE accounts SET balance = -1 WHERE id = :id"), {"id": user["account_id"]})


def test_duplicate_phone_rejected(engine, make_user):
    make_user(phone="01011112222")
    with pytest.raises(IntegrityError):
        make_user(phone="01011112222")


def test_seed_products(engine):
    with engine.connect() as conn:
        codes = set(conn.execute(text("SELECT code FROM loan_products")).scalars())
    assert codes == {"car", "jeonse", "home"}


def test_seed_merchants(engine):
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM merchants")).scalar_one()
        regions = conn.execute(text("SELECT COUNT(DISTINCT region) FROM merchants")).scalar_one()
    assert count == 30
    assert regions == 10


def _insert_session(conn, user_id, token_hash="a" * 64, client="web", end_reason=None):
    conn.execute(
        text("INSERT INTO sessions (token_hash, user_id, device_id, client, user_agent, last_seen_at, end_reason)"
             " VALUES (:t, :u, :d, :c, 'pytest', UTC_TIMESTAMP(6), :r)"),
        {"t": token_hash, "u": user_id, "d": "11111111-1111-1111-1111-111111111111", "c": client, "r": end_reason},
    )


def test_session_token_hash_unique(engine, make_user):
    user = make_user()
    with engine.begin() as conn:
        _insert_session(conn, user["id"])
    with pytest.raises(IntegrityError), engine.begin() as conn:
        _insert_session(conn, user["id"])


@pytest.mark.parametrize("column", ["client", "end_reason"])
def test_session_values_checked(engine, make_user, column):
    user = make_user()
    values = {"client": "web", "end_reason": None, column: "unknown"}
    with pytest.raises((IntegrityError, OperationalError)), engine.begin() as conn:
        _insert_session(conn, user["id"], **values)


def test_session_login_method_checked(engine, make_user):
    user = make_user()
    with pytest.raises((IntegrityError, OperationalError)), engine.begin() as conn:
        conn.execute(
            text("INSERT INTO sessions (token_hash, user_id, device_id, login_method, last_seen_at)"
                 " VALUES (:t, :u, :d, 'carrier-pigeon', UTC_TIMESTAMP(6))"),
            {"t": "b" * 64, "u": user["id"], "d": "11111111-1111-1111-1111-111111111111"},
        )


def test_kakao_subject_unique(engine, make_user):
    make_user(kakao_subject="kakao-same")
    with pytest.raises(IntegrityError):
        make_user(kakao_subject="kakao-same")
