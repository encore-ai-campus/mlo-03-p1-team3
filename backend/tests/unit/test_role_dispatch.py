"""Permission checks must preserve results without occupying a worker thread."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.deps import CurrentUser, current_user, require_customer
from app.core.errors import install_error_handlers


@pytest.mark.parametrize("role,status", [("customer", 200), ("bank_employee", 403)])
def test_customer_role_check_avoids_worker_dispatch(role, status, monkeypatch):
    import fastapi.dependencies.utils as dependencies

    dispatched = []
    original = dependencies.run_in_threadpool

    async def record_dispatch(function, *args, **kwargs):
        dispatched.append(function)
        return await original(function, *args, **kwargs)

    monkeypatch.setattr(dependencies, "run_in_threadpool", record_dispatch)
    app = FastAPI()
    install_error_handlers(app)

    async def identity():
        return CurrentUser(id=1, role=role, name="test")

    app.dependency_overrides[current_user] = identity

    @app.get("/role")
    async def endpoint(user=Depends(require_customer)):
        return {"id": user.id}

    with TestClient(app) as client:
        response = client.get("/role")
    assert response.status_code == status
    assert require_customer not in dispatched
    if status == 403:
        assert response.json()["code"] == "forbidden"
