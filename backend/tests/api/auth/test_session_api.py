"""로그인·가입·로그아웃이 서버 세션과 기기 쿠키를 쓰는지 API로 확인한다."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.time import kst_now
from app.main import create_app

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
DEVICE = "33333333-3333-4333-8333-333333333333"


def _login(client, user, headers=None):
    return client.post(LOGIN, json={"phone_number": user["phone"], "password": user["password"]}, headers=headers)


def _sessions(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT user_id, device_id, client, user_agent, end_reason FROM sessions"
                                 " ORDER BY id")).mappings().all()


def test_login_sets_device_cookie_and_stores_client(client, engine, make_user):
    user = make_user()

    response = _login(client, user, headers={"X-Client": "ios-app", "User-Agent": "PodoBank-iOS/1.0"})

    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    device_cookie = next(c for c in cookies if c.startswith("podobank_device="))
    assert "HttpOnly" in device_cookie and f"Max-Age={365 * 24 * 3600}" in device_cookie
    [row] = _sessions(engine)
    assert (row["user_id"], row["client"], row["user_agent"], row["end_reason"]) == (
        user["id"], "ios-app", "PodoBank-iOS/1.0", None)
    assert client.get(ME).status_code == 200


def test_unknown_client_header_saved_as_web(client, engine, make_user):
    _login(client, make_user(), headers={"X-Client": "toaster"})
    assert _sessions(engine)[0]["client"] == "web"


def test_same_device_relogin_replaces_session(client, engine, make_user):
    user = make_user()
    _login(client, user)
    old_cookie = client.cookies.get("podobank_session")

    _login(client, user)

    rows = _sessions(engine)
    assert [r["end_reason"] for r in rows] == ["replaced", None]
    assert rows[0]["device_id"] == rows[1]["device_id"]
    client.cookies.set("podobank_session", old_cookie)
    assert client.get(ME).status_code == 401


def test_two_devices_keep_two_sessions(settings, engine, make_user):
    user = make_user()
    app = create_app(settings)
    with TestClient(app) as pc, TestClient(app) as phone:
        _login(pc, user)
        _login(phone, user, headers={"X-Client": "android-app"})
        assert pc.get(ME).status_code == 200
        assert phone.get(ME).status_code == 200

    rows = _sessions(engine)
    assert len({r["device_id"] for r in rows}) == 2
    assert [r["end_reason"] for r in rows] == [None, None]


def test_logout_ends_session_on_server(client, engine, make_user):
    user = make_user()
    _login(client, user)
    cookie = client.cookies.get("podobank_session")

    assert client.post("/api/v1/auth/logout").status_code == 200

    assert _sessions(engine)[0]["end_reason"] == "logout"
    client.cookies.set("podobank_session", cookie)  # 지운 쿠키를 다시 넣어도 서버가 막는다
    assert client.get(ME).status_code == 401


def test_idle_session_401(client, engine, make_user):
    user = make_user()
    _login(client, user)
    with engine.begin() as conn:
        conn.execute(text("UPDATE sessions SET last_seen_at = :t"), {"t": kst_now() - timedelta(minutes=11)})

    response = client.get(ME)

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"
    assert _sessions(engine)[0]["end_reason"] == "idle_timeout"


def test_forged_cookie_401(client, make_user):
    make_user()
    client.cookies.set("podobank_session", "forged-value")
    assert client.get(ME).status_code == 401


def test_signup_starts_session_with_client(client, engine):
    body = {"name": "김포도", "phone_number": "01012345678", "password": "password123", "birth_year": 1998,
            "gender": "female", "marital_status": "single", "is_employed": True}

    response = client.post("/api/v1/auth/signup", json=body, headers={"X-Client": "android-app"})

    assert response.status_code == 200
    assert _sessions(engine)[0]["client"] == "android-app"
    assert client.get(ME).status_code == 200


def test_parallel_login_same_device_leaves_one_session(settings, engine, make_user):
    user = make_user()
    app = create_app(settings)

    def attempt(_):
        with TestClient(app, cookies={"podobank_device": DEVICE}) as c:
            return _login(c, user).status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        statuses = list(pool.map(attempt, range(5)))

    rows = _sessions(engine)
    assert statuses == [200] * 5
    assert {r["device_id"] for r in rows} == {DEVICE}
    assert [r["end_reason"] for r in rows].count(None) == 1
