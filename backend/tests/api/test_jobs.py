import json

from sqlalchemy import text

from app.api.events.service import FORBIDDEN_KEYS
from app.jobs.reconcile import reconcile
from tests.conftest import login, recorded_events


def test_reconcile_clean(client, make_user, engine, sink):
    sender, receiver = make_user(balance=100_000), make_user()
    login(client, sender)
    client.post("/api/v1/transfers", json={"recipient": receiver["account_number"], "amount": 30_000})

    result = reconcile(engine, sink)

    assert result.checked == 2
    assert result.mismatched_account_ids == []
    events = recorded_events("reconciliation")
    assert len(events) == 1
    assert (events[0]["outcome"], events[0]["source"]) == ("success", "batch")
    assert events[0]["properties"] == {"checked_accounts": 2, "mismatched_accounts": 0}


def test_reconcile_detects_mismatch(make_user, engine, sink):
    broken = make_user(balance=5_000)
    make_user(balance=1_000)  # 원장과 맞는 계좌
    make_user()  # 원장 없는 0원 계좌는 일치
    with engine.begin() as conn:
        conn.execute(text("UPDATE accounts SET balance = balance + 1 WHERE id = :a"), {"a": broken["account_id"]})

    result = reconcile(engine, sink)

    assert result.checked == 3
    assert result.mismatched_account_ids == [broken["account_id"]]
    event = recorded_events("reconciliation")[0]
    assert (event["outcome"], event["reason"]) == ("failure", "ledger_mismatch")
    assert event["properties"] == {"checked_accounts": 3, "mismatched_accounts": 1}
    assert not FORBIDDEN_KEYS & set(event["properties"])
    assert str(broken["account_id"]) not in json.dumps(event["properties"])
