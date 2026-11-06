from datetime import timedelta

from sqlalchemy import text

from app.core.time import kst_now
from tests.conftest import recorded_events


def _login(client, phone, password):
    return client.post("/api/v1/auth/login", json={"phone_number": phone, "password": password})


def test_login_success_sets_cookie(client, make_user, engine):
    user = make_user()

    response = _login(client, user["phone"], user["password"])

    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "podobank_session=" in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    assert "Max-Age=3600" in cookie
    events = recorded_events("login")
    assert [(e["outcome"], e["properties"]["method"]) for e in events] == [("success", "password")]


def test_wrong_password_401(client, make_user, engine):
    user = make_user()

    response = _login(client, user["phone"], "wrong-password")

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"
    assert [e["reason"] for e in recorded_events("login")] == ["invalid_credentials"]


def test_unknown_phone_same_401(client, make_user):
    user = make_user()
    wrong_pw = _login(client, user["phone"], "wrong-password").json()
    unknown = _login(client, "01099999999", "wrong-password").json()

    assert unknown["code"] == wrong_pw["code"]
    assert unknown["message"] == wrong_pw["message"]


def test_lock_after_5_failures(client, make_user):
    user = make_user()
    for _ in range(5):
        assert _login(client, user["phone"], "wrong-password").status_code == 401

    response = _login(client, user["phone"], user["password"])

    assert response.status_code == 423
    assert response.json()["code"] == "account_locked"


def test_lock_expires_after_5_minutes(client, make_user, engine):
    user = make_user()
    for _ in range(5):
        _login(client, user["phone"], "wrong-password")
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET locked_until = :t WHERE id = :id"),
                     {"t": kst_now() - timedelta(seconds=1), "id": user["id"]})

    assert _login(client, user["phone"], user["password"]).status_code == 200
    with engine.connect() as conn:
        count = conn.execute(text("SELECT failed_login_count FROM users WHERE id = :id"), {"id": user["id"]}).scalar()
    assert count == 0


def test_wrong_password_after_lock_expiry_starts_fresh(client, make_user, engine):
    user = make_user()
    for _ in range(5):
        _login(client, user["phone"], "wrong-password")
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET locked_until = :t WHERE id = :id"),
                     {"t": kst_now() - timedelta(seconds=1), "id": user["id"]})

    assert _login(client, user["phone"], "wrong-password").status_code == 401
    assert _login(client, user["phone"], user["password"]).status_code == 200


def test_me_and_logout(client, make_user):
    user = make_user(name="김포도")
    _login(client, user["phone"], user["password"])

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json() == {"id": user["id"], "name": "김포도", "role": "customer"}

    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_no_cookie_401(client):
    assert client.get("/api/v1/auth/me").status_code == 401
