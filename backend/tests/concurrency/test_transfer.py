from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.time import kst_now
from app.main import create_app
from tests.api.transfers.test_transfer import add_transfer_out
from tests.conftest import ledger_matches_balance, login


def balances(engine, *account_ids):
    with engine.connect() as conn:
        return [conn.execute(text("SELECT balance FROM accounts WHERE id = :a"), {"a": a}).scalar()
                for a in account_ids]


def send(app, user, to_account, amount):
    with TestClient(app) as c:
        login(c, user)
        return c.post("/api/v1/transfers", json={"recipient": to_account, "amount": amount}).status_code


def test_opposite_transfers_no_deadlock(settings, engine, make_user):
    a, b = make_user(balance=1_000_000), make_user(balance=1_000_000)
    app = create_app(settings)
    jobs = [(a, b["account_number"]) for _ in range(20)] + [(b, a["account_number"]) for _ in range(20)]

    with ThreadPoolExecutor(max_workers=20) as pool:
        statuses = list(pool.map(lambda job: send(app, job[0], job[1], 1_000), jobs))

    assert set(statuses) <= {200, 409}
    assert sum(balances(engine, a["account_id"], b["account_id"])) == 2_000_000
    assert ledger_matches_balance(engine, a["account_id"])
    assert ledger_matches_balance(engine, b["account_id"])


def test_daily_limit_race(settings, engine, make_user):
    sender, receiver = make_user(balance=200_000_000), make_user()
    add_transfer_out(engine, sender["account_id"], 90_000_000, kst_now())
    app = create_app(settings)

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: send(app, sender, receiver["account_number"], 8_000_000), range(2)))

    assert sorted(statuses) == [200, 422]


def test_pool_exhaustion_no_500(settings, engine, make_user):
    sender, receiver = make_user(balance=10_000_000), make_user()
    app = create_app(settings)

    with ThreadPoolExecutor(max_workers=50) as pool:
        statuses = list(pool.map(lambda _: send(app, sender, receiver["account_number"], 1_000), range(50)))

    assert set(statuses) <= {200, 409, 503}
    assert ledger_matches_balance(engine, sender["account_id"])
    assert ledger_matches_balance(engine, receiver["account_id"])
