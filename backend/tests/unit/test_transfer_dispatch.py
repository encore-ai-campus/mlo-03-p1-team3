"""Database work stays off the loop without a second response-validation dispatch."""
import threading
from importlib import import_module

import anyio.to_thread
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.deps import CurrentUser, session_token
from app.core.errors import AppError, install_error_handlers


@pytest.mark.parametrize("path,body,result", [
    ("/accounts/me", None, {"account_number": "test", "balance": 100}),
    ("/transfers/recipient-lookup", {"query": "test"}, {"name": "test"}),
    ("/transfers", {"recipient": "test", "amount": 10}, {"transaction_id": "test", "balance": 90}),
])
@pytest.mark.parametrize("fails", [False, True])
def test_transfer_path_uses_one_worker_dispatch(monkeypatch, path, body, result, fails):
    accounts = import_module("app.api.accounts.router")
    transfers = import_module("app.api.transfers.router")
    app = FastAPI()
    app.state.engine = object()
    app.include_router(accounts.router)
    app.include_router(transfers.router)
    install_error_handlers(app)
    loop_threads, worker_threads, dispatches = [], [], []

    async def identity():
        loop_threads.append(threading.get_ident())
        return CurrentUser(1, "customer", "test")

    app.dependency_overrides[session_token] = identity

    def read(request, token, fn):
        return fn(None, CurrentUser(1, "customer", "test"))

    def money(request, token, fn):
        return fn(CurrentUser(1, "customer", "test"))

    monkeypatch.setattr(accounts, "run_customer_read", read)
    monkeypatch.setattr(transfers, "run_customer_read", read)
    monkeypatch.setattr(transfers, "run_customer", money)

    def work(*args, **kwargs):
        worker_threads.append(threading.get_ident())
        if fails:
            raise AppError(409, "test_failure", "test")
        return result

    monkeypatch.setattr(accounts.repository, "find_by_user", work)
    monkeypatch.setattr(transfers.service, "lookup_on", work)
    monkeypatch.setattr(transfers, "run_money", work)
    original = anyio.to_thread.run_sync

    async def record(function, *args, **kwargs):
        dispatches.append(function)
        return await original(function, *args, **kwargs)

    monkeypatch.setattr(anyio.to_thread, "run_sync", record)
    with TestClient(app) as client:
        response = client.get(path) if body is None else client.post(path, json=body)
    assert response.status_code == (409 if fails else 200)
    if not fails:
        assert response.json() == result
    assert len(dispatches) == 1
    assert len(worker_threads) == 1
    assert worker_threads[0] != loop_threads[0]
