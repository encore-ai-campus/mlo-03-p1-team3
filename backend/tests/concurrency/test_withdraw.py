from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ledger_matches_balance, login


def test_parallel_withdrawals(settings, engine, make_user):
    user = make_user(balance=100_000)
    app = create_app(settings)

    def withdraw(_):
        with TestClient(app) as c:
            login(c, user)
            return c.post("/api/v1/transactions/withdrawal", json={"amount": 30_000}).status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        statuses = list(pool.map(withdraw, range(10)))

    assert statuses.count(200) == 3
    assert set(statuses) <= {200, 409}
    with TestClient(app) as c:
        login(c, user)
        assert c.get("/api/v1/accounts/me").json()["balance"] == 10_000
    assert ledger_matches_balance(engine, user["account_id"])


def test_parallel_deposits_all_applied(settings, engine, make_user):
    user = make_user()
    app = create_app(settings)

    def deposit(_):
        with TestClient(app) as c:
            login(c, user)
            return c.post("/api/v1/transactions/deposit", json={"amount": 1_000}).status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        statuses = list(pool.map(deposit, range(5)))

    assert statuses == [200] * 5
    with TestClient(app) as c:
        login(c, user)
        assert c.get("/api/v1/accounts/me").json()["balance"] == 5_000
    assert ledger_matches_balance(engine, user["account_id"])
