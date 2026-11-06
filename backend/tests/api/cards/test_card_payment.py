
from sqlalchemy import text

from app.api.events.service import FORBIDDEN_KEYS
from tests.conftest import ledger_matches_balance, logged_events, login, recorded_events

PAY = "/api/v1/cards/payments"


def first_merchant(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT id, region, category FROM merchants ORDER BY id LIMIT 1")).mappings().one()


def count(engine, table):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()


def test_my_card(client, make_user, engine):
    user = make_user()
    login(client, user)
    with engine.connect() as conn:
        number = conn.execute(text("SELECT card_number FROM cards WHERE account_id = :a"),
                              {"a": user["account_id"]}).scalar()

    assert client.get("/api/v1/cards/me").json() == {"card_last4": number[-4:]}


def test_merchants_list(client, make_user):
    login(client, make_user())

    merchants = client.get("/api/v1/merchants").json()

    assert len(merchants) == 30
    assert set(merchants[0]) == {"id", "name", "category", "region"}


def test_payment_success(client, make_user, engine):
    user = make_user(balance=50_000)
    merchant = first_merchant(engine)
    login(client, user)

    response = client.post(PAY, json={"merchant_id": merchant["id"], "amount": 4_500})

    assert response.status_code == 200
    assert response.json()["balance"] == 45_500
    with engine.connect() as conn:
        payment = conn.execute(text("SELECT transaction_id, amount, merchant_id FROM card_payments")).one()
        entry = conn.execute(text("SELECT transaction_id, amount FROM ledger_entries WHERE entry_type = 'card_payment'")).one()
    assert payment.transaction_id == entry.transaction_id == response.json()["transaction_id"]
    assert (payment.amount, entry.amount, payment.merchant_id) == (4_500, -4_500, merchant["id"])
    assert ledger_matches_balance(engine, user["account_id"])
    events = recorded_events("card_payment")
    assert [(e["outcome"], e["properties"]["region"], e["properties"]["merchant_category"]) for e in events] == [
        ("success", merchant["region"], merchant["category"])]
    assert len(recorded_events(collection="card_payment_locations")) == 1
    assert [e["event_type"] for e in logged_events()] == ["login", "card_payment"]  # 위치 로그는 events.log에 안 씀


def test_payment_insufficient_409(client, make_user, engine):
    user = make_user(balance=1_000)
    login(client, user)

    response = client.post(PAY, json={"merchant_id": first_merchant(engine)["id"], "amount": 4_500})

    assert response.status_code == 409
    assert response.json()["code"] == "insufficient_funds"
    assert count(engine, "card_payments") == 0
    assert ledger_matches_balance(engine, user["account_id"])
    assert recorded_events(collection="card_payment_locations") == []


def test_unknown_merchant_404(client, make_user):
    login(client, make_user(balance=10_000))

    response = client.post(PAY, json={"merchant_id": 999_999, "amount": 1_000})

    assert response.status_code == 404
    assert response.json()["code"] == "merchant_not_found"


def test_payment_amount_rules(client, make_user, engine):
    login(client, make_user(balance=10_000))
    merchant_id = first_merchant(engine)["id"]

    zero = client.post(PAY, json={"merchant_id": merchant_id, "amount": 0})
    over = client.post(PAY, json={"merchant_id": merchant_id, "amount": 10_000_001})

    assert (zero.json()["code"], over.json()["code"]) == ("invalid_amount", "amount_limit_exceeded")


def test_location_event_has_no_person_data(client, make_user, engine):
    login(client, make_user(balance=50_000))
    client.post(PAY, json={"merchant_id": first_merchant(engine)["id"], "amount": 4_500})

    [payload] = recorded_events(collection="card_payment_locations")

    def keys(value):
        if isinstance(value, dict):
            return set(value) | set().union(*(keys(v) for v in value.values()))
        return set()

    assert not keys(payload) & FORBIDDEN_KEYS
    assert set(payload["properties"]) == {"region", "lat", "lng", "merchant_category"}


def test_employee_cannot_pay_403(client, make_user, engine):
    login(client, make_user(role="bank_employee"))

    response = client.post(PAY, json={"merchant_id": first_merchant(engine)["id"], "amount": 1_000})

    assert response.status_code == 403
