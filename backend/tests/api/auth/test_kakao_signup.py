"""카카오 로그인·가입. 카카오는 '누구인지 확인'만 하고, 로그인 유지는 로컬 로그인과 같은 서버 세션을 쓴다."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.auth.kakao import KakaoAuthError, KakaoProfile, KakaoUnavailableError
from app.core.time import kst_now
from app.main import create_app
from tests.conftest import logged_events, recorded_events

SIGNUP = {"phone_number": "01012345678", "password": "password123", "birth_year": 1998,
          "gender": "male", "marital_status": "single", "is_employed": True}
ME = "/api/v1/auth/me"


class FakeKakao:
    def __init__(self, subject="kakao-1", name="홍길동", fail=None):
        self.subject, self.name, self.fail = subject, name, fail

    def authorization_url(self, state: str) -> str:
        return f"https://kauth.example/authorize?state={state}"

    def fetch_profile(self, code: str) -> KakaoProfile:
        if self.fail:
            raise self.fail("fake")
        return KakaoProfile(subject=self.subject, name=self.name)


@pytest.fixture
def kakao_app(settings, engine):
    app = create_app(settings)
    app.state.kakao = FakeKakao()
    return app


@pytest.fixture
def kc(kakao_app):
    with TestClient(kakao_app) as client:
        yield client


def kakao_login(client, headers=None):
    state = client.post("/api/v1/auth/kakao/start").json()["authorization_url"].split("state=")[1]
    return client.post("/api/v1/auth/kakao/login", json={"code": "c", "state": state}, headers=headers)


def kakao_signup(client, body=None):
    return client.post("/api/v1/auth/kakao/signup", json=body or SIGNUP)


def _sessions(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT user_id, client, login_method, end_reason FROM sessions ORDER BY id")
                            ).mappings().all()


def test_start_returns_url_with_state_cookie(kc):
    response = kc.post("/api/v1/auth/kakao/start")

    assert response.status_code == 200
    assert "state=" in response.json()["authorization_url"]
    assert "podobank_kakao_state=" in response.headers["set-cookie"]


def test_state_mismatch_401(kc):
    kc.post("/api/v1/auth/kakao/start")

    response = kc.post("/api/v1/auth/kakao/login", json={"code": "c", "state": "wrong"})

    assert response.status_code == 401
    assert response.json()["code"] == "kakao_state_invalid"


def test_new_user_needs_registration_and_pending_row_has_hash_only(kc, engine):
    response = kakao_login(kc)

    assert response.json() == {"status": "registration_required"}
    raw = kc.cookies.get("podobank_kakao_signup")
    with engine.connect() as conn:
        row = conn.execute(text("SELECT token_hash, kakao_subject, name FROM kakao_signups")).mappings().one()
    assert (row["kakao_subject"], row["name"]) == ("kakao-1", "홍길동")
    assert raw and row["token_hash"] != raw and len(row["token_hash"]) == 64
    assert _sessions(engine) == []
    assert kc.get(ME).status_code == 401


def test_kakao_signup_creates_user_and_kakao_session(kc, engine):
    kakao_login(kc, headers={"X-Client": "ios-app"})

    response = kakao_signup(kc)

    assert response.json() == {"status": "authenticated"}
    assert kc.get(ME).json()["name"] == "홍길동"
    with engine.connect() as conn:
        user = conn.execute(text("SELECT kakao_subject, phone_number FROM users")).one()
        pending = conn.execute(text("SELECT COUNT(*) FROM kakao_signups")).scalar()
    assert tuple(user) == ("kakao-1", "01012345678")
    assert pending == 0
    [session] = _sessions(engine)
    assert (session["login_method"], session["end_reason"]) == ("kakao", None)
    [event] = recorded_events("signup")
    assert event["properties"] == {"method": "kakao"}


def test_kakao_user_can_login_with_phone_and_password(kc, engine):
    """카카오 가입 때 정한 전화번호·비밀번호로 로컬 로그인도 된다."""
    kakao_login(kc)
    kakao_signup(kc)
    kc.post("/api/v1/auth/logout")

    response = kc.post("/api/v1/auth/login", json={"phone_number": SIGNUP["phone_number"],
                                                   "password": SIGNUP["password"]})

    assert response.status_code == 200
    assert kc.get(ME).json()["name"] == "홍길동"
    assert [s["login_method"] for s in _sessions(engine)] == ["kakao", "password"]


def test_existing_kakao_user_logs_in_directly(kakao_app, engine, make_user):
    user = make_user(kakao_subject="kakao-1")
    with TestClient(kakao_app) as client:
        response = kakao_login(client, headers={"X-Client": "android-app"})
        assert client.get(ME).json()["id"] == user["id"]
        assert "podobank_device" in client.cookies

    assert response.json() == {"status": "authenticated"}
    [session] = _sessions(engine)
    assert (session["user_id"], session["client"], session["login_method"]) == (user["id"], "android-app", "kakao")
    events = recorded_events("login")
    assert [(e["outcome"], e["properties"]["method"]) for e in events] == [("success", "kakao")]


def test_signup_without_pending_cookie_401(kc):
    response = kakao_signup(kc)

    assert response.status_code == 401
    assert response.json()["code"] == "signup_session_expired"


def test_expired_pending_signup_401(kc, engine):
    kakao_login(kc)
    with engine.begin() as conn:
        conn.execute(text("UPDATE kakao_signups SET expires_at = :t"), {"t": kst_now() - timedelta(seconds=1)})

    response = kakao_signup(kc)

    assert response.status_code == 401
    assert response.json()["code"] == "signup_session_expired"


def test_pending_signup_cannot_be_reused(kc, engine):
    kakao_login(kc)
    pending = kc.cookies.get("podobank_kakao_signup")
    kakao_signup(kc)

    kc.cookies.set("podobank_kakao_signup", pending, path="/api/v1/auth/kakao")
    response = kakao_signup(kc, {**SIGNUP, "phone_number": "01099998888"})

    assert response.status_code == 401
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM users")).scalar() == 1


def test_kakao_signup_duplicate_phone_409(kc, make_user):
    make_user(phone=SIGNUP["phone_number"])
    kakao_login(kc)

    response = kakao_signup(kc)

    assert response.status_code == 409
    assert response.json()["code"] == "phone_already_registered"


def test_employee_cannot_use_kakao(kakao_app, make_user):
    make_user(role="bank_employee", kakao_subject="kakao-1")
    with TestClient(kakao_app) as client:
        response = kakao_login(client)

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"


def test_locked_account_blocked_on_kakao(kakao_app, engine, make_user):
    user = make_user(kakao_subject="kakao-1")
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET locked_until = :t WHERE id = :id"),
                     {"t": kst_now() + timedelta(minutes=5), "id": user["id"]})
    with TestClient(kakao_app) as client:
        response = kakao_login(client)

    assert response.status_code == 423
    assert response.json()["code"] == "account_locked"


@pytest.mark.parametrize(("error", "status", "code"), [
    (KakaoUnavailableError, 503, "kakao_unavailable"),
    (KakaoAuthError, 401, "kakao_authorization_failed"),
])
def test_kakao_failures(kakao_app, error, status, code):
    kakao_app.state.kakao = FakeKakao(fail=error)
    with TestClient(kakao_app) as client:
        response = kakao_login(client)

    assert response.status_code == status
    assert response.json()["code"] == code


def test_local_login_works_when_kakao_down(kakao_app, make_user):
    kakao_app.state.kakao = FakeKakao(fail=KakaoUnavailableError)
    user = make_user()
    with TestClient(kakao_app) as client:
        response = client.post("/api/v1/auth/login", json={"phone_number": user["phone"], "password": user["password"]})

    assert response.status_code == 200


def test_kakao_subject_never_in_events(kc):
    kakao_login(kc)
    kakao_signup(kc)

    for event in logged_events():
        assert "kakao-1" not in str(event)
