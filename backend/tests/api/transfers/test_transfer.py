from datetime import timedelta

from sqlalchemy import text

from app.core.time import kst_day_range, kst_now
from tests.conftest import ledger_matches_balance, login, recorded_events

LOOKUP = "/api/v1/transfers/recipient-lookup"
TRANSFER = "/api/v1/transfers"


def add_transfer_out(engine, account_id, amount, created_at):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO ledger_entries (transaction_id, account_id, entry_type, amount, balance_after,"
                          " created_at) VALUES (UUID(), :a, 'transfer_out', :m, 0, :t)"),
                     {"a": account_id, "m": -amount, "t": created_at})


def test_lookup_by_phone_shows_full_name_only(client, make_user):
    login(client, make_user())
    target = make_user(name="홍길동")

    response = client.post(LOOKUP, json={"query": target["phone"]})

    assert response.status_code == 200
    assert response.json() == {"name": "홍길동"}


def test_lookup_by_account_number(client, make_user):
    login(client, make_user())
    target = make_user(name="이산")

    response = client.post(LOOKUP, json={"query": target["account_number"]})

    assert response.json() == {"name": "이산"}


def test_transfer_by_phone(client, make_user, engine):
    sender, receiver = make_user(balance=100_000), make_user()
    login(client, sender)
    hyphenated = f"{receiver['phone'][:3]}-{receiver['phone'][3:7]}-{receiver['phone'][7:]}"

    response = client.post(TRANSFER, json={"recipient": hyphenated, "amount": 30_000})

    assert response.status_code == 200
    with engine.connect() as conn:
        assert conn.execute(text("SELECT balance FROM accounts WHERE id = :a"),
                            {"a": receiver["account_id"]}).scalar() == 30_000


def test_lookup_not_found_404(client, make_user):
    login(client, make_user())

    response = client.post(LOOKUP, json={"query": "01000000000"})

    assert response.status_code == 404
    assert response.json()["code"] == "recipient_not_found"


def test_lookup_employee_not_found(client, make_user):
    login(client, make_user())
    employee = make_user(role="bank_employee")

    assert client.post(LOOKUP, json={"query": employee["phone"]}).status_code == 404


def test_transfer_success_pair(client, make_user, engine):
    sender, receiver = make_user(balance=100_000), make_user()
    login(client, sender)

    response = client.post(TRANSFER, json={"recipient": receiver["account_number"], "amount": 30_000})

    assert response.status_code == 200
    assert response.json()["balance"] == 70_000
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT transaction_id, entry_type, amount FROM ledger_entries"
                                 " WHERE entry_type LIKE 'transfer_%' ORDER BY id")).all()
    assert [(r.entry_type, r.amount) for r in rows] == [("transfer_out", -30_000), ("transfer_in", 30_000)]
    assert rows[0].transaction_id == rows[1].transaction_id == response.json()["transaction_id"]
    assert ledger_matches_balance(engine, sender["account_id"])
    assert ledger_matches_balance(engine, receiver["account_id"])
    assert [e["outcome"] for e in recorded_events("transfer")] == ["success"]


def test_self_transfer_422(client, make_user):
    user = make_user(balance=10_000)
    login(client, user)

    response = client.post(TRANSFER, json={"recipient": user["account_number"], "amount": 1_000})

    assert response.status_code == 422
    assert response.json()["code"] == "self_transfer"


def test_unknown_account_404(client, make_user):
    login(client, make_user(balance=10_000))

    response = client.post(TRANSFER, json={"recipient": "100-0000-0000", "amount": 1_000})

    assert response.status_code == 404
    assert response.json()["code"] == "recipient_not_found"


def test_insufficient_409_no_change(client, make_user, engine):
    sender, receiver = make_user(balance=10_000), make_user()
    login(client, sender)

    response = client.post(TRANSFER, json={"recipient": receiver["account_number"], "amount": 10_001})

    assert response.status_code == 409
    assert response.json()["code"] == "insufficient_funds"
    assert ledger_matches_balance(engine, sender["account_id"])
    assert ledger_matches_balance(engine, receiver["account_id"])
    with engine.connect() as conn:
        assert conn.execute(text("SELECT balance FROM accounts WHERE id = :a"),
                            {"a": receiver["account_id"]}).scalar() == 0


def test_over_single_limit_422(client, make_user):
    sender, receiver = make_user(balance=20_000_000), make_user()
    login(client, sender)

    response = client.post(TRANSFER, json={"recipient": receiver["account_number"], "amount": 10_000_001})

    assert response.json()["code"] == "amount_limit_exceeded"


def test_daily_limit_422(client, make_user, engine):
    sender, receiver = make_user(balance=10_000_000), make_user()
    add_transfer_out(engine, sender["account_id"], 95_000_000, kst_now())
    login(client, sender)

    response = client.post(TRANSFER, json={"recipient": receiver["account_number"], "amount": 6_000_000})

    assert response.status_code == 422
    assert response.json()["code"] == "daily_limit_exceeded"


def test_kst_boundary_yesterday_not_counted(client, make_user, engine):
    sender, receiver = make_user(balance=10_000_000), make_user()
    today_start_kst, _ = kst_day_range(kst_now())
    add_transfer_out(engine, sender["account_id"], 95_000_000, today_start_kst - timedelta(minutes=1))
    login(client, sender)

    response = client.post(TRANSFER, json={"recipient": receiver["account_number"], "amount": 6_000_000})

    assert response.status_code == 200
