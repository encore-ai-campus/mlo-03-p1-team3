from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.core.security import SESSION_COOKIE
from app.main import create_app
from tests.conftest import TEST_MARIADB_URL, login, make_settings

DOWN_URL = "mysql+pymysql://root:test@127.0.0.1:1/podobank_test"


def test_read_api_db_down_503():
    settings = make_settings(mariadb_url=DOWN_URL)
    with TestClient(create_app(settings)) as client:
        client.cookies.set(SESSION_COOKIE, "any-session-value")  # 세션 확인에서 DB를 부른다
        response = client.get("/api/v1/accounts/me")

    assert response.status_code == 503
    assert response.json()["code"] == "database_unavailable"


def test_login_db_down_503():
    with TestClient(create_app(make_settings(mariadb_url=DOWN_URL))) as client:
        response = client.post("/api/v1/auth/login", json={"phone_number": "01012345678", "password": "password123"})

    assert response.status_code == 503
    assert response.json()["code"] == "database_unavailable"


def test_pool_exhausted_on_auth_503(settings, make_user):
    user = make_user()
    app = create_app(settings)
    tiny = create_engine(TEST_MARIADB_URL, pool_size=1, max_overflow=0, pool_timeout=0.2)
    with TestClient(app) as client:
        login(client, user)
        app.state.engine = tiny
        with tiny.connect():  # 하나뿐인 연결을 붙잡아 둔다
            response = client.get("/api/v1/accounts/me")

    assert response.status_code == 503
    assert response.json()["code"] == "database_unavailable"
