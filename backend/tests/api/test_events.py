"""이벤트는 커밋 뒤에만 events.log와 MongoDB에 한 번씩 쓴다."""
import pytest
from fastapi.testclient import TestClient

from app.api.events.service import FORBIDDEN_KEYS, EventSink, record, transaction
from app.main import create_app
from tests import conftest
from tests.conftest import TEST_EVENT_LOG, logged_events, login, make_settings, recorded_events


def test_transfer_event_once_in_log_and_mongo(client, make_user):
    sender, receiver = make_user(balance=100_000), make_user()
    login(client, sender)

    assert client.post("/api/v1/transfers", json={"recipient": receiver["account_number"],
                                                  "amount": 30_000}).status_code == 200

    [logged] = logged_events("transfer")
    [stored] = recorded_events("transfer")
    assert logged == stored
    assert (logged["outcome"], logged["reason"]) == ("success", "completed")
    assert "_id" not in logged
    assert not FORBIDDEN_KEYS & set(logged) and not FORBIDDEN_KEYS & set(logged["properties"])


def test_failed_transfer_only_failure_event(client, make_user):
    sender, receiver = make_user(balance=1_000), make_user()
    login(client, sender)

    response = client.post("/api/v1/transfers", json={"recipient": receiver["account_number"], "amount": 30_000})

    assert response.status_code == 409
    assert [(e["outcome"], e["reason"]) for e in logged_events("transfer")] == [("failure", "insufficient_funds")]
    assert [(e["outcome"], e["reason"]) for e in recorded_events("transfer")] == [("failure", "insufficient_funds")]


def test_rolled_back_transaction_writes_nothing(engine, sink):
    with pytest.raises(RuntimeError, match="boom"), transaction(engine, sink) as conn:
        record(conn, None, "deposit", "success", "completed", source="batch")
        raise RuntimeError("boom")

    assert logged_events() == [] and recorded_events() == []


def test_committed_transaction_writes_once(engine, sink):
    with transaction(engine, sink) as conn:
        record(conn, None, "deposit", "success", "completed", source="batch")

    assert len(logged_events("deposit")) == len(recorded_events("deposit")) == 1


def test_record_outside_transaction_is_error(engine):
    with pytest.raises(RuntimeError), engine.begin() as conn:
        record(conn, None, "deposit", "success", "completed")


def test_location_log_goes_to_mongo_only(engine, sink):
    with transaction(engine, sink) as conn:
        record(conn, None, "card_payment_location", "success", "completed", collection="card_payment_locations")

    assert logged_events() == []
    assert len(recorded_events(collection="card_payment_locations")) == 1


def test_publish_never_raises_after_commit(sink):
    """커밋 뒤에는 어떤 이유로 이벤트 쓰기가 실패해도 예외가 나면 안 된다(돈은 이미 저장됨)."""
    broken = {"event_id": "x", "event_type": "deposit", "properties": {"bad": object()}}

    sink.publish([("events_bronze", broken)])

    assert logged_events() == [] and recorded_events() == []


def test_event_carries_instance_name(engine):
    """FastAPI가 2대라 서버마다 events.log가 따로 쌓인다. 이벤트에 어느 서버에서 났는지 남긴다."""
    sink = EventSink(conftest.test_mongo(), TEST_EVENT_LOG, instance="api-2")
    with transaction(engine, sink) as conn:
        record(conn, None, "deposit", "success", "completed", source="batch")

    assert [e["instance"] for e in logged_events("deposit")] == ["api-2"]
    assert [e["instance"] for e in recorded_events("deposit")] == ["api-2"]


def test_api_events_use_instance_from_settings(engine, make_user):
    user = make_user()
    with TestClient(create_app(make_settings(instance_name="api-1"))) as c:
        c.post("/api/v1/auth/login", json={"phone_number": user["phone"], "password": user["password"]})

    assert [e["instance"] for e in logged_events("login")] == ["api-1"]
