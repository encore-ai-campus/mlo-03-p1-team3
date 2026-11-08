"""Customer dispatch uses fake connections only; no database is required."""
from contextlib import contextmanager
from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

import anyio.to_thread
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.api.auth import service as auth
from app.core import deps
from app.core.errors import AppError, install_error_handlers
from app.core.security import SESSION_COOKIE
from app.core.time import kst_now


class Engine:
    def __init__(self):
        self.leases = 0
        self.commits = 0
        self.closed = False

    @contextmanager
    def connect(self):
        self.leases += 1
        try:
            yield self
        finally:
            self.closed = True

    @contextmanager
    def begin(self):
        with self.connect() as conn:
            yield conn
            self.commit()

    def commit(self):
        self.commits += 1


PATHS = [
    ("/accounts/me", None, {"account_number": "test", "balance": 100}),
    ("/transfers/recipient-lookup", {"query": "test"}, {"name": "test"}),
    ("/transfers", {"recipient": "test", "amount": 10}, {"transaction_id": "test", "balance": 90}),
]


@pytest.mark.parametrize("path,body,result", PATHS)
@pytest.mark.parametrize("case,status", [
    ("ok", 200), ("missing_cookie", 401), ("missing_session", 401),
    ("idle", 401), ("max_age", 401), ("employee", 403), ("business_error", 409),
    ("pool_error", 503), ("db_error", 503), ("unexpected", 500),
])
def test_customer_paths(monkeypatch, path, body, result, case, status):
    accounts = import_module("app.api.accounts.router")
    transfers = import_module("app.api.transfers.router")
    engine = Engine()
    app = FastAPI()
    app.state.engine = engine
    app.include_router(accounts.router)
    app.include_router(transfers.router)
    install_error_handlers(app)
    now = kst_now()
    monkeypatch.setattr(deps, "kst_now", lambda: now)
    seen, ended, touched, work, dispatches = [], [], [], [], []
    error = AppError(409, "business_failure", "test")

    def find(conn, token):
        seen.append(conn)
        if case == "pool_error":
            raise PoolTimeoutError()
        if case == "db_error":
            raise OperationalError("select", {}, Exception(2003, "unavailable"))
        if case == "missing_session":
            return None
        return {
            "id": 7, "user_id": 1, "name": "test",
            "role": "bank_employee" if case == "employee" else "customer",
            "last_seen_at": now - timedelta(minutes=10 if case == "idle" else 1),
            "created_at": now - timedelta(minutes=60 if case == "max_age" else 2),
        }

    monkeypatch.setattr(auth.repository, "find_active_session", find)
    monkeypatch.setattr(auth.repository, "end_session", lambda *args: ended.append(args))
    monkeypatch.setattr(auth.repository, "touch_session", lambda *args: touched.append(args))

    def business(conn, *args):
        assert conn is engine
        work.append(conn)
        if case == "business_error":
            raise error
        if case == "unexpected":
            raise RuntimeError("unexpected")
        return result

    def money(request, event, props, action):
        assert engine.closed and engine.commits == 1
        assert event == "transfer"
        return action(engine)

    monkeypatch.setattr(accounts.repository, "find_by_user", business)
    monkeypatch.setattr(transfers.service, "lookup_on", business)
    monkeypatch.setattr(transfers.service, "transfer", business)
    monkeypatch.setattr(transfers, "run_money", money)
    original = anyio.to_thread.run_sync

    async def dispatch(fn, *args, **kwargs):
        dispatches.append(fn)
        return await original(fn, *args, **kwargs)

    monkeypatch.setattr(anyio.to_thread, "run_sync", dispatch)
    with TestClient(app, raise_server_exceptions=False) as client:
        if case != "missing_cookie":
            client.cookies.set(SESSION_COOKIE, "token")
        response = client.get(path) if body is None else client.post(path, json=body)
    assert response.status_code == status
    assert len(dispatches) == (0 if case == "missing_cookie" else 1)
    assert engine.leases == (0 if case == "missing_cookie" else 1)
    assert bool(work) == (case in {"ok", "business_error", "unexpected"})
    assert bool(ended) == (case in {"idle", "max_age"})
    if ended:
        assert ended[0][2] == ("idle_timeout" if case == "idle" else "max_age")
    if case in {"ok", "business_error", "employee", "missing_session", "idle", "max_age"}:
        assert engine.commits == 1
    if case in {"pool_error", "db_error"}:
        assert response.json()["code"] == "database_unavailable"
        assert engine.commits == 0
    if case == "unexpected":
        assert engine.commits == (1 if path == "/transfers" else 0)
    if case == "business_error":
        assert response.json()["code"] == error.code
    if case == "ok":
        assert response.json() == result
        assert touched[0][0] is seen[0] is work[0]


@pytest.mark.parametrize("path", ["/transfers", "/transfers/recipient-lookup"])
@pytest.mark.parametrize("cookie,status", [(False, 401), (True, 422)])
def test_body_validation_order(path, cookie, status):
    app = FastAPI()
    app.include_router(import_module("app.api.transfers.router").router)
    install_error_handlers(app)
    with TestClient(app) as client:
        if cookie:
            client.cookies.set(SESSION_COOKIE, "invalid")
        response = client.post(path, json={})
    assert response.status_code == status


def test_read_preserves_app_error_identity():
    engine = Engine()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(engine=engine)))
    error = AppError(404, "missing", "test")

    def action(conn, user):
        raise error

    with (
        patch.object(deps, "customer_on", return_value=deps.CurrentUser(1, "customer", "test")),
        pytest.raises(AppError) as caught,
    ):
        deps.run_customer_read(request, "token", action)
    assert caught.value is error
    assert engine.commits == 1


@pytest.mark.parametrize("seconds,touches", [(59, 0), (60, 1), (61, 1)])
def test_session_touch_boundary(monkeypatch, seconds, touches):
    now = kst_now()
    conn = Engine()
    row = {
        "id": 7, "user_id": 1, "role": "customer", "name": "test",
        "last_seen_at": now - timedelta(seconds=seconds),
        "created_at": now - timedelta(minutes=2),
    }
    seen = []
    monkeypatch.setattr(auth.repository, "find_active_session", lambda *args: row)
    monkeypatch.setattr(auth.repository, "touch_session", lambda *args: seen.append(args))
    assert auth.resolve_session_on(conn, "token", now) == auth.SessionUser(1, "customer", "test")
    assert len(seen) == touches
    assert conn.commits == 0
    if seen:
        assert seen[0] == (conn, 7, now, now - timedelta(seconds=60))
