from types import SimpleNamespace

import pytest

from app.api.transfers import service
from app.core.errors import AppError


@pytest.fixture
def transfer_fake(monkeypatch):
    state = SimpleNamespace(
        sender={"id": 9, "balance": 999_999}, receiver={"id": 2},
        locked=[{"id": 2, "balance": 700}, {"id": 9, "balance": 5_000}],
        sent=0, updated=True, calls=[],
    )

    def fake(name, result):
        def call(conn, *args):
            state.calls.append((name, args))
            return result()
        return call

    monkeypatch.setattr(service.accounts, "find_by_user", fake("sender", lambda: state.sender))
    monkeypatch.setattr(service, "find_recipient", fake("recipient", lambda: state.receiver))
    monkeypatch.setattr(service.accounts, "lock_pair", fake("lock", lambda: state.locked))
    monkeypatch.setattr(service.repository, "sent_between", fake("limit", lambda: state.sent))
    monkeypatch.setattr(service.accounts, "apply_transfer", fake("update", lambda: state.updated))
    monkeypatch.setattr(service.accounts, "insert_transfer_ledger", fake("ledger", lambda: None))
    monkeypatch.setattr(service, "record", fake("event", lambda: None))
    for name in ("lock", "add_balance", "balance_of", "insert_ledger"):
        def forbidden(*args, **kwargs):
            pytest.fail("legacy money operation called")
        monkeypatch.setattr(service.accounts, name, forbidden)
    return state


def run_transfer():
    return service.transfer(object(), None, 42, "100-0000-0002", 1_000)


def test_success_uses_locked_balances_and_batched_calls(transfer_fake):
    result = run_transfer()
    calls = transfer_fake.calls
    assert [name for name, _ in calls] == ["sender", "recipient", "lock", "limit", "update", "ledger", "event"]
    assert calls[2][1] == (2, 9)
    assert calls[4][1] == (9, 2, 1_000)
    assert calls[5][1] == (result["transaction_id"], 9, 2, 1_000, 4_000, 1_700)
    assert result == {"transaction_id": result["transaction_id"], "balance": 4_000}
    assert calls[6][1] == (None, "transfer", "success", "completed", {"amount_band": "under_10k"})


@pytest.mark.parametrize("failure,status,code,expected", [
    ("sender", 404, "account_not_found", ["sender"]),
    ("recipient", 404, "recipient_not_found", ["sender", "recipient"]),
    ("self", 422, "self_transfer", ["sender", "recipient"]),
    ("locked_sender", 404, "account_not_found", ["sender", "recipient", "lock"]),
    ("locked_recipient", 404, "recipient_not_found", ["sender", "recipient", "lock"]),
    ("locked_both", 404, "account_not_found", ["sender", "recipient", "lock"]),
    ("funds", 409, "insufficient_funds", ["sender", "recipient", "lock", "limit"]),
    ("update", 409, "insufficient_funds", ["sender", "recipient", "lock", "limit", "update"]),
    ("limit", 422, "daily_limit_exceeded", ["sender", "recipient", "lock", "limit"]),
])
def test_transfer_failures(transfer_fake, failure, status, code, expected):
    state = transfer_fake
    if failure == "sender":
        state.sender = None
    elif failure == "recipient":
        state.receiver = None
    elif failure == "self":
        state.receiver = {"id": 9}
    elif failure.startswith("locked_"):
        missing = {"locked_sender": {9}, "locked_recipient": {2}, "locked_both": {2, 9}}[failure]
        state.locked = [row for row in state.locked if row["id"] not in missing]
    elif failure in ("funds", "limit"):
        state.locked[1]["balance"] = 999
        if failure == "limit":
            state.sent = service.TRANSFER_DAILY_LIMIT
    elif failure == "update":
        state.updated = False
    with pytest.raises(AppError) as exc:
        run_transfer()
    assert (exc.value.status, exc.value.code) == (status, code)
    assert [name for name, _ in state.calls] == expected


@pytest.mark.parametrize("rowcount,expected", [(0, False), (1, False), (2, True), (-1, False)])
def test_apply_transfer_rowcount(rowcount, expected):
    from app.api.accounts.repository import apply_transfer

    class Connection:
        def execute(self, statement, parameters):
            assert str(statement).startswith("UPDATE accounts")
            assert parameters == {"s": 9, "r": 2, "neg": -1_000, "pos": 1_000}
            return SimpleNamespace(rowcount=rowcount)

    assert apply_transfer(Connection(), 9, 2, 1_000) is expected
