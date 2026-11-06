import itertools
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.events.service import EventSink
from app.core.config import Settings
from app.core.security import hash_password
from app.db.mariadb import make_engine
from app.db.migrate import apply_migrations
from app.db.mongodb import make_mongo
from app.main import create_app

# 테스트 전용 DB 주소. 각자 PC의 MariaDB·MongoDB에 맞게 환경변수로 바꿀 수 있다. 테스트가 테이블을 비우므로 운영 DB를 넣지 않는다.
TEST_MARIADB_URL = os.environ.get("TEST_MARIADB_URL", "mysql+pymysql://root:test@127.0.0.1:3306/podobank_test")
TEST_MONGODB_URL = os.environ.get("TEST_MONGODB_URL", "mongodb://127.0.0.1:27017")
TEST_MONGODB_DB = "podobank_test"
TEST_EVENT_LOG = Path("./var/test-log/events.log")


def make_settings(**overrides) -> Settings:
    values = {
        "mariadb_url": TEST_MARIADB_URL,
        "mongodb_url": TEST_MONGODB_URL,
        "mongodb_db": TEST_MONGODB_DB,
        "event_log_path": str(TEST_EVENT_LOG),
        "app_log_path": "./var/test-log/app.log",
    }
    values.update(overrides)
    return Settings(**values)


SEED_TABLES = {"loan_products", "merchants", "schema_migrations"}
_phone_seq = itertools.count(1)
_password_hash = None


@pytest.fixture(scope="session")
def engine():
    eng = make_engine(TEST_MARIADB_URL)
    apply_migrations(eng)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def clean_db(request):
    if "engine" not in request.fixturenames and "client" not in request.fixturenames:
        yield
        return
    eng = request.getfixturevalue("engine")
    with eng.begin() as conn:
        tables = conn.execute(text("SHOW TABLES")).scalars().all()
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in tables:
            if table not in SEED_TABLES:
                conn.execute(text(f"DELETE FROM `{table}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    test_mongo().client.drop_database(TEST_MONGODB_DB)
    TEST_EVENT_LOG.unlink(missing_ok=True)
    yield


@pytest.fixture
def make_user(engine):
    """users + accounts + cards를 직접 만든다. 기본 비밀번호는 'password123'."""

    def _make(role="customer", phone=None, password="password123", balance=0, name="홍길동",
              is_employed=True, kakao_subject=None):
        global _password_hash
        if password == "password123":
            _password_hash = _password_hash or hash_password(password)
            pw_hash = _password_hash
        else:
            pw_hash = hash_password(password)
        seq = next(_phone_seq)
        phone = phone or f"0109{seq:07d}"
        with engine.begin() as conn:
            user_id = conn.execute(
                text(
                    "INSERT INTO users (kakao_subject, phone_number, password_hash, name, birth_year, gender,"
                    " marital_status, is_employed, role) VALUES (:k, :p, :h, :n, 1995, 'male', 'single', :e, :r)"
                ),
                {"k": kakao_subject, "p": phone, "h": pw_hash, "n": name, "e": is_employed, "r": role},
            ).lastrowid
            account_id = conn.execute(
                text("INSERT INTO accounts (user_id, account_number, balance) VALUES (:u, :a, :b)"),
                {"u": user_id, "a": f"100-{seq:04d}-{user_id:04d}", "b": balance},
            ).lastrowid
            if balance:
                conn.execute(
                    text(
                        "INSERT INTO ledger_entries (transaction_id, account_id, entry_type, amount, balance_after)"
                        " VALUES (UUID(), :a, 'deposit', :b, :b)"
                    ),
                    {"a": account_id, "b": balance},
                )
            conn.execute(
                text("INSERT INTO cards (account_id, card_number) VALUES (:a, :c)"),
                {"a": account_id, "c": f"9410{seq:012d}"},
            )
        return {"id": user_id, "phone": phone, "password": password, "account_id": account_id,
                "account_number": f"100-{seq:04d}-{user_id:04d}", "name": name}

    return _make


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def client(settings, engine):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def login(client, user):
    response = client.post("/api/v1/auth/login", json={"phone_number": user["phone"], "password": user["password"]})
    assert response.status_code == 200, response.text
    return client


def ledger_matches_balance(engine, account_id) -> bool:
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COALESCE(SUM(amount), 0) FROM ledger_entries WHERE account_id = :a"),
                             {"a": account_id}).scalar()
        balance = conn.execute(text("SELECT balance FROM accounts WHERE id = :a"), {"a": account_id}).scalar()
    return int(total) == balance


def test_mongo():
    return make_mongo(TEST_MONGODB_URL, TEST_MONGODB_DB)


@pytest.fixture
def sink() -> EventSink:
    """배치 작업에 넘기는 sink. API와 같은 테스트 MongoDB·events.log에 쓴다."""
    return EventSink(test_mongo(), TEST_EVENT_LOG)


def recorded_events(event_type=None, collection="events_bronze") -> list[dict]:
    """MongoDB에 들어간 이벤트를 넣은 순서대로 돌려준다(_id 제외)."""
    docs = test_mongo()[collection].find({}, {"_id": 0}).sort("_id", 1)
    return [d for d in docs if event_type is None or d["event_type"] == event_type]


def logged_events(event_type=None) -> list[dict]:
    """events.log에 쓴 이벤트(한 줄에 JSON 1개)."""
    if not TEST_EVENT_LOG.exists():
        return []
    events = [json.loads(line) for line in TEST_EVENT_LOG.read_text(encoding="utf-8").splitlines()]
    return [e for e in events if event_type is None or e["event_type"] == event_type]
