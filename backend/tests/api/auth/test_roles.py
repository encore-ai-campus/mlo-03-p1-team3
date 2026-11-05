import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from app.core.deps import CurrentUser, require_customer, require_employee
from app.main import create_app

router = APIRouter()


@router.get("/only-customer")
def only_customer(user: CurrentUser = Depends(require_customer)):
    return {"id": user.id}


@router.get("/only-employee")
def only_employee(user: CurrentUser = Depends(require_employee)):
    return {"id": user.id}


@pytest.fixture
def role_client(settings, engine):
    app = create_app(settings)
    app.include_router(router)
    with TestClient(app) as client:
        yield client


def _login(client, user):
    client.post("/api/v1/auth/login", json={"phone_number": user["phone"], "password": user["password"]})


def test_customer_on_employee_dependency_403(role_client, make_user):
    _login(role_client, make_user())

    response = role_client.get("/only-employee")

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_employee_on_customer_dependency_403(role_client, make_user):
    _login(role_client, make_user(role="bank_employee"))

    assert role_client.get("/only-customer").status_code == 403


def test_customer_on_customer_dependency_ok(role_client, make_user):
    _login(role_client, make_user())

    assert role_client.get("/only-customer").status_code == 200
