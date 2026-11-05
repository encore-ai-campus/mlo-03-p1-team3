from sqlalchemy import text

from tests.conftest import ledger_matches_balance, login, recorded_events


def test_deposit_updates_balance_and_ledger(client, make_user, engine):
    user = make_user(balance=10_000)
    login(client, user)

    response = client.post("/api/v1/transactions/deposit", json={"amount": 50_000})

    assert response.status_code == 200
    assert response.json()["balance"] == 60_000
    assert ledger_matches_balance(engine, user["account_id"])
    with engine.connect() as conn:
        last = conn.execute(text("SELECT entry_type, amount, balance_after FROM ledger_entries"
                                 " WHERE account_id = :a ORDER BY id DESC LIMIT 1"), {"a": user["account_id"]}).one()
    assert tuple(last) == ("deposit", 50_000, 60_000)
    events = recorded_events("deposit")
    assert [(e["outcome"], e["properties"]["amount_band"]) for e in events] == [("success", "under_100k")]


def test_withdraw_success(client, make_user, engine):
    user = make_user(balance=10_000)
    login(client, user)

    response = client.post("/api/v1/transactions/withdrawal", json={"amount": 3_000})

    assert response.json()["balance"] == 7_000
    assert ledger_matches_balance(engine, user["account_id"])


def test_withdraw_insufficient_409(client, make_user, engine):
    user = make_user(balance=10_000)
    login(client, user)

    response = client.post("/api/v1/transactions/withdrawal", json={"amount": 10_001})

    assert response.status_code == 409
    assert response.json()["code"] == "insufficient_funds"
    assert client.get("/api/v1/accounts/me").json()["balance"] == 10_000
    assert ledger_matches_balance(engine, user["account_id"])
    assert [e["reason"] for e in recorded_events("withdrawal")] == ["insufficient_funds"]


def test_amount_zero_422(client, make_user):
    login(client, make_user())

    response = client.post("/api/v1/transactions/deposit", json={"amount": 0})

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_amount"


def test_amount_over_limit_422(client, make_user):
    login(client, make_user())

    response = client.post("/api/v1/transactions/deposit", json={"amount": 10_000_001})

    assert response.status_code == 422
    assert response.json()["code"] == "amount_limit_exceeded"


def test_amount_not_integer_422(client, make_user):
    login(client, make_user())

    assert client.post("/api/v1/transactions/deposit", json={"amount": 1.5}).status_code == 422


def test_employee_deposit_403(client, make_user):
    login(client, make_user(role="bank_employee"))

    assert client.post("/api/v1/transactions/deposit", json={"amount": 100}).status_code == 403


def test_account_and_ledger_view(client, make_user):
    user = make_user(balance=5_000)
    login(client, user)
    client.post("/api/v1/transactions/withdrawal", json={"amount": 1_000})

    account = client.get("/api/v1/accounts/me").json()
    ledger = client.get("/api/v1/accounts/me/ledger?limit=10").json()

    assert account == {"account_number": user["account_number"], "balance": 4_000}
    assert [item["entry_type"] for item in ledger["items"]] == ["withdrawal", "deposit"]
    assert ledger["items"][0]["amount"] == -1_000 and ledger["items"][0]["balance_after"] == 4_000


def test_ledger_limit_validation(client, make_user):
    login(client, make_user())

    assert client.get("/api/v1/accounts/me/ledger?limit=101").status_code == 422


def test_ledger_time_is_utc_with_z(client, make_user):
    from datetime import UTC, datetime

    login(client, make_user(balance=5_000))

    created_at = client.get("/api/v1/accounts/me/ledger").json()["items"][0]["created_at"]

    assert created_at.endswith("Z")
    parsed = datetime.fromisoformat(created_at)
    assert abs((datetime.now(UTC) - parsed).total_seconds()) < 60
