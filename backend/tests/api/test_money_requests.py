"""중복 요청 방지 키를 쓰지 않는다. 돈이 움직이는 요청은 헤더 없이 처리된다."""
from sqlalchemy import text

from tests.conftest import ledger_matches_balance, login


def ledger_count(engine, account_id):
    with engine.connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM ledger_entries WHERE account_id = :a"), {"a": account_id}).scalar()


def test_money_request_needs_no_key(client, make_user, engine):
    user = make_user()
    login(client, user)

    response = client.post("/api/v1/transactions/deposit", json={"amount": 1_000})

    assert response.status_code == 200
    assert response.json()["balance"] == 1_000
    assert ledger_matches_balance(engine, user["account_id"])


def test_same_request_twice_is_processed_twice(client, make_user, engine):
    user = make_user()
    login(client, user)

    first = client.post("/api/v1/transactions/deposit", json={"amount": 1_000})
    second = client.post("/api/v1/transactions/deposit", json={"amount": 1_000})

    assert first.status_code == second.status_code == 200
    assert first.json()["transaction_id"] != second.json()["transaction_id"]
    assert ledger_count(engine, user["account_id"]) == 2
    assert client.get("/api/v1/accounts/me").json()["balance"] == 2_000


def test_validation_error_keeps_fields(client, make_user):
    login(client, make_user())

    response = client.post("/api/v1/transactions/deposit", json={"amount": 1.5})

    assert response.status_code == 422
    assert response.json()["fields"] == {"amount": "형식이 올바르지 않습니다"}
