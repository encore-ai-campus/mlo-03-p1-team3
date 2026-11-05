import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import AppError
from app.main import create_app
from tests.conftest import make_settings


class Body(BaseModel):
    amount: int


router = APIRouter()


@router.get("/boom/app-error")
def app_error():
    raise AppError(409, "insufficient_funds", "잔액이 부족합니다")


@router.post("/boom/validate")
def validate(body: Body):
    return {"ok": True}


@router.get("/boom/crash")
def crash():
    raise RuntimeError("secret internal detail")


@pytest.fixture
def boom_client():
    app = create_app(make_settings())
    app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_app_error_shape(boom_client):
    response = boom_client.get("/boom/app-error")

    assert response.status_code == 409
    body = response.json()
    assert set(body) == {"code", "message", "request_id"}
    assert body["code"] == "insufficient_funds"


def test_validation_error_shape(boom_client):
    response = boom_client.post("/boom/validate", json={"amount": "abc"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert "amount" in body["fields"]


def test_unhandled_error_hides_detail(boom_client):
    response = boom_client.get("/boom/crash")

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "secret" not in response.text


def test_request_id_header(boom_client):
    response = boom_client.get("/boom/app-error")

    assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_not_found_route_uses_error_shape(boom_client):
    response = boom_client.get("/api/v1/no-such-route")

    assert response.status_code == 404
    assert set(response.json()) >= {"code", "message", "request_id"}
