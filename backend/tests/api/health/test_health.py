from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings


def test_health_ok(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"mariadb": "ok", "mongodb": "ok"}


def test_health_mariadb_down():
    settings = make_settings(mariadb_url="mysql+pymysql://root:test@127.0.0.1:1/podobank_test")

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json()["code"] == "database_unavailable"


def test_health_mongodb_down():
    settings = make_settings(mongodb_url="mongodb://127.0.0.1:1")

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["mongodb"] == "down"
