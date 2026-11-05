"""MongoDB나 app.log가 실패해도 돈 처리는 성공한다."""
import time

from fastapi.testclient import TestClient

from app.db.mongodb import make_mongo
from app.main import create_app
from tests.conftest import (
    TEST_MONGODB_URL,
    ledger_matches_balance,
    logged_events,
    login,
    make_settings,
    recorded_events,
)


def test_transfer_ok_when_mongo_down(engine, make_user):
    sender, receiver = make_user(balance=100_000), make_user()
    app = create_app(make_settings(mongodb_url="mongodb://127.0.0.1:1"))

    with TestClient(app) as client:
        login(client, sender)
        started = time.monotonic()
        response = client.post("/api/v1/transfers", json={"recipient": receiver["account_number"], "amount": 30_000})
        elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert elapsed < 2  # MongoDB를 짧게만 기다린다
    assert ledger_matches_balance(engine, sender["account_id"])
    assert [e["outcome"] for e in logged_events("transfer")] == ["success"]  # app.log에는 남는다
    assert recorded_events("transfer") == []


def test_transfer_ok_when_event_log_fails(engine, make_user, tmp_path):
    sender, receiver = make_user(balance=100_000), make_user()
    app = create_app(make_settings(event_log_path=str(tmp_path)))  # 폴더라서 파일로 열 수 없다

    with TestClient(app) as client:
        login(client, sender)
        response = client.post("/api/v1/transfers", json={"recipient": receiver["account_number"], "amount": 30_000})

    assert response.status_code == 200
    assert ledger_matches_balance(engine, sender["account_id"])
    assert [e["outcome"] for e in recorded_events("transfer")] == ["success"]  # MongoDB에는 남는다


def test_app_starts_when_mongo_down(engine):
    with TestClient(create_app(make_settings(mongodb_url="mongodb://127.0.0.1:1"))) as client:
        assert client.get("/api/v1/health").json()["mongodb"] == "down"


def test_mongo_client_has_short_timeouts():
    options = make_mongo(TEST_MONGODB_URL, "podobank_test").client.options

    assert options.server_selection_timeout == 0.5
    assert options.pool_options.socket_timeout == 2
