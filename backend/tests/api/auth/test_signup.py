"""가입: 이름·전화번호·비밀번호 등을 직접 입력한다."""
from sqlalchemy import text

from tests.conftest import recorded_events

SIGNUP = "/api/v1/auth/signup"
BODY = {"name": "김포도", "phone_number": "01012345678", "password": "password123", "birth_year": 1998,
        "gender": "female", "marital_status": "single", "is_employed": True}


def test_signup_creates_user_account_card_and_logs_in(client, engine):
    response = client.post(SIGNUP, json=BODY)

    assert response.status_code == 200
    assert response.json() == {"status": "authenticated"}
    assert "podobank_session=" in response.headers["set-cookie"]
    assert client.get("/api/v1/auth/me").json()["name"] == "김포도"
    assert client.get("/api/v1/accounts/me").json()["balance"] == 0
    assert "card_last4" in client.get("/api/v1/cards/me").json()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT role, is_employed FROM users")).one()
    assert tuple(row) == ("customer", 1)
    [event] = recorded_events("signup")
    assert (event["outcome"], event["properties"]) == ("success", {"method": "password"})


def test_signup_then_password_login(client):
    client.post(SIGNUP, json=BODY)
    client.post("/api/v1/auth/logout")

    response = client.post("/api/v1/auth/login", json={"phone_number": BODY["phone_number"],
                                                       "password": BODY["password"]})

    assert response.status_code == 200


def test_duplicate_phone_409(client, make_user):
    make_user(phone=BODY["phone_number"])

    response = client.post(SIGNUP, json=BODY)

    assert response.status_code == 409
    assert response.json()["code"] == "phone_already_registered"
    assert [e["reason"] for e in recorded_events("signup")] == ["phone_already_registered"]


def test_invalid_fields_422(client):
    bad = {**BODY, "name": " ", "phone_number": "010-12", "password": "short", "gender": "x"}

    response = client.post(SIGNUP, json=bad)

    assert response.status_code == 422
    assert set(response.json()["fields"]) == {"name", "phone_number", "password", "gender"}


def test_name_is_trimmed(client):
    client.post(SIGNUP, json={**BODY, "name": "  김포도  "})

    assert client.get("/api/v1/auth/me").json()["name"] == "김포도"
