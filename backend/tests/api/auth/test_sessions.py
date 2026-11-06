"""서버 세션: 만들기, 확인(미사용 10분·최대 60분), 1분 간격 기록, 끝내기, 같은 기기 재로그인."""
from datetime import timedelta

from sqlalchemy import text

from app.api.auth import service
from app.core.time import kst_now

DEVICE_A = "11111111-1111-4111-8111-111111111111"
DEVICE_B = "22222222-2222-4222-8222-222222222222"


def _start(engine, user, now, device=DEVICE_A, client="web"):
    with engine.begin() as conn:
        return service.start_session(conn, user["id"], device, client, "pytest-agent", now)


def _row(engine, token):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT user_id, device_id, client, user_agent, created_at, last_seen_at, ended_at, end_reason"
                 " FROM sessions WHERE token_hash = :h"), {"h": service.hash_token(token)},
        ).mappings().one()


def test_start_stores_hash_not_token(engine, make_user):
    user = make_user()
    now = kst_now()
    token = _start(engine, user, now, client="ios-app")

    row = _row(engine, token)
    assert (row["user_id"], row["device_id"], row["client"], row["user_agent"]) == (
        user["id"], DEVICE_A, "ios-app", "pytest-agent")
    assert row["ended_at"] is None
    with engine.connect() as conn:
        stored = conn.execute(text("SELECT token_hash FROM sessions")).scalar_one()
    assert stored != token and len(stored) == 64


def test_resolve_returns_user(engine, make_user):
    user = make_user(name="김포도")
    now = kst_now()
    token = _start(engine, user, now)

    found = service.resolve_session(engine, token, now + timedelta(minutes=9))

    assert (found.id, found.role, found.name) == (user["id"], "customer", "김포도")


def test_unknown_token_is_none(engine, make_user):
    make_user()
    assert service.resolve_session(engine, "not-a-session", kst_now()) is None


def test_idle_10_minutes_ends_session(engine, make_user):
    user = make_user()
    now = kst_now()
    token = _start(engine, user, now)

    assert service.resolve_session(engine, token, now + timedelta(minutes=10)) is None
    assert _row(engine, token)["end_reason"] == "idle_timeout"
    assert service.resolve_session(engine, token, now + timedelta(minutes=10, seconds=1)) is None


def test_use_extends_idle_but_not_past_60_minutes(engine, make_user):
    user = make_user()
    now = kst_now()
    token = _start(engine, user, now)

    for minute in range(9, 60, 9):  # 9분마다 쓰면 미사용 만료에 걸리지 않는다
        assert service.resolve_session(engine, token, now + timedelta(minutes=minute)) is not None
    assert service.resolve_session(engine, token, now + timedelta(minutes=60)) is None
    assert _row(engine, token)["end_reason"] == "max_age"


def test_last_seen_written_at_most_once_per_minute(engine, make_user):
    user = make_user()
    now = kst_now()
    token = _start(engine, user, now)

    service.resolve_session(engine, token, now + timedelta(seconds=30))
    assert _row(engine, token)["last_seen_at"] == now

    service.resolve_session(engine, token, now + timedelta(seconds=61))
    service.resolve_session(engine, token, now + timedelta(seconds=90))
    assert _row(engine, token)["last_seen_at"] == now + timedelta(seconds=61)


def test_end_session_logout(engine, make_user):
    user = make_user()
    now = kst_now()
    token = _start(engine, user, now)

    service.end_session(engine, token, now + timedelta(minutes=1))

    assert _row(engine, token)["end_reason"] == "logout"
    assert service.resolve_session(engine, token, now + timedelta(minutes=2)) is None


def test_same_device_login_replaces_old_session(engine, make_user):
    user = make_user()
    now = kst_now()
    old = _start(engine, user, now)
    new = _start(engine, user, now + timedelta(minutes=1))

    assert _row(engine, old)["end_reason"] == "replaced"
    assert service.resolve_session(engine, old, now + timedelta(minutes=2)) is None
    assert service.resolve_session(engine, new, now + timedelta(minutes=2)) is not None


def test_other_device_sessions_both_alive(engine, make_user):
    user = make_user()
    now = kst_now()
    first = _start(engine, user, now, device=DEVICE_A)
    second = _start(engine, user, now, device=DEVICE_B, client="android-app")

    assert service.resolve_session(engine, first, now + timedelta(minutes=1)) is not None
    assert service.resolve_session(engine, second, now + timedelta(minutes=1)) is not None


def test_normalize_client():
    assert service.normalize_client(None) == "web"
    assert service.normalize_client("ios-app") == "ios-app"
    assert service.normalize_client("android-app") == "android-app"
    assert service.normalize_client("hacker'; DROP") == "web"


def test_normalize_device_id():
    assert service.normalize_device_id(DEVICE_A) == DEVICE_A
    fresh = service.normalize_device_id("not-a-uuid")
    assert fresh != "not-a-uuid" and len(fresh) == 36
    assert service.normalize_device_id(None) != service.normalize_device_id(None)
