import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from pymongo.errors import AutoReconnect
from sqlalchemy.exc import OperationalError

from app.api.events.service import EventSink
from app.core.config import Settings
from app.core.errors import AppError, install_error_handlers
from app.observability.application_log import ApplicationLog, install_application_log
from app.observability.request_id import install_request_id


def make_app(path, instance="api-1"):
    app = FastAPI()
    install_request_id(app)
    install_error_handlers(app)
    install_application_log(app, ApplicationLog(path, instance))

    @app.get("/api/v1/accounts/{account_id}")
    def account(account_id: str):
        return {"ok": True}

    @app.post("/api/v1/failure")
    def failure():
        raise AppError(409, "insufficient_funds", "잔액이 부족합니다")

    @app.get("/api/v1/crash")
    def crash():
        raise RuntimeError("secret-password phone=01012345678")

    @app.get("/api/v1/db-error")
    def db_error():
        raise OperationalError("secret-sql", {"password": "secret"}, RuntimeError("secret"))

    class Body(BaseModel):
        amount: int

    @app.post("/api/v1/validate")
    def validate(body: Body):
        return {"ok": True}

    return app


@pytest.mark.parametrize("method,path,status,level,code", [
    ("GET", "/api/v1/accounts/private-account?token=secret", 200, "INFO", None),
    ("POST", "/api/v1/failure", 409, "WARNING", "insufficient_funds"),
    ("GET", "/api/v1/crash", 500, "ERROR", "internal_error"),
    ("GET", "/private-unmatched", 404, "WARNING", "not_found"),
    ("PUT", "/api/v1/accounts/private-account", 405, "WARNING", "method_not_allowed"),
    ("GET", "/api/v1/db-error", 503, "ERROR", "database_unavailable"),
    ("POST", "/api/v1/validate", 422, "WARNING", "validation_error"),
])
def test_request_logged_once_without_private_values(tmp_path, method, path, status, level, code):
    log_path = tmp_path / "app.log"
    with TestClient(make_app(log_path), raise_server_exceptions=False) as client:
        response = client.request(
            method, path,
            headers={"Cookie": "session=secret-cookie", "Authorization": "Bearer secret-token"},
            json={"amount": "secret-amount", "phone_number": "01012345678"},
        )
    assert response.status_code == status
    [entry] = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert entry["level"] == level
    assert entry["status_code"] == status
    assert entry["error_code"] == code
    assert entry["request_id"] == response.headers["x-request-id"]
    assert entry["duration_ms"] >= 0
    assert entry["instance"] == "api-1"
    text = log_path.read_text()
    for secret in ("private-account", "private-unmatched", "secret", "01012345678", "session="):
        assert secret not in text
    if status == 200:
        assert entry["route"] == "/api/v1/accounts/{account_id}"
    if status in (500, 503):
        assert entry["exception_type"] == ("RuntimeError" if status == 500 else "OperationalError")
        assert any(frame["function"] == ("crash" if status == 500 else "db_error") for frame in entry["stack"])


def test_log_failure_does_not_change_response(tmp_path):
    with TestClient(make_app(tmp_path)) as client:
        assert client.get("/api/v1/accounts/123").status_code == 200


def test_log_paths_must_be_separate(tmp_path):
    with pytest.raises(ValueError, match="must be different"):
        Settings("unused", "unused", "unused", event_log_path=str(tmp_path / "app.log"),
                 app_log_path=str(tmp_path / "app.log"))


def test_instances_write_separate_files(tmp_path):
    for instance in ("api-1", "api-2"):
        with TestClient(make_app(tmp_path / f"{instance}.log", instance)) as client:
            assert client.get("/api/v1/accounts/123").status_code == 200
    for instance in ("api-1", "api-2"):
        assert json.loads((tmp_path / f"{instance}.log").read_text())["instance"] == instance


def test_concurrent_application_logs_are_complete_json_lines(tmp_path):
    sink = ApplicationLog(tmp_path / "app.log", "api-1")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda index: sink.write("INFO", "request_completed", request_id=str(index)), range(100)))
    entries = [json.loads(line) for line in sink.path.read_text().splitlines()]
    assert len(entries) == 100
    assert len({entry["request_id"] for entry in entries}) == 100


def test_request_logging_continues_after_external_rotation(tmp_path):
    path = tmp_path / "app.log"
    rotated = tmp_path / "app.log.1"
    with TestClient(make_app(path)) as client:
        first = client.get("/api/v1/accounts/123")
        path.rename(rotated)
        path.touch(mode=0o640)
        second = client.get("/api/v1/accounts/456")
    assert first.status_code == second.status_code == 200
    assert json.loads(rotated.read_text())["request_id"] == first.headers["x-request-id"]
    assert json.loads(path.read_text())["request_id"] == second.headers["x-request-id"]


def test_event_logging_continues_after_external_rotation(tmp_path):
    path = tmp_path / "events.log"
    mongo = MagicMock()
    sink = EventSink(mongo, path)
    first = {"event_id": "first", "event_type": "deposit"}
    second = {"event_id": "second", "event_type": "deposit"}
    sink.publish([("events_bronze", first)])
    rotated = path.rename(tmp_path / "events.log.1")
    path.touch(mode=0o640)
    sink.publish([("events_bronze", second)])
    assert json.loads(rotated.read_text())["event_id"] == "first"
    assert json.loads(path.read_text())["event_id"] == "second"
    assert mongo.__getitem__.return_value.insert_one.call_count == 2


@pytest.mark.parametrize("mongo_down,file_down", [(False, False), (True, False), (False, True)])
def test_events_and_application_warnings_use_separate_files(tmp_path, mongo_down, file_down):
    mongo = MagicMock()
    if mongo_down:
        mongo.__getitem__.return_value.insert_one.side_effect = AutoReconnect("secret-connection")
    app_log = ApplicationLog(tmp_path / "app.log", "api-1")
    event_path = tmp_path if file_down else tmp_path / "events.log"
    sink = EventSink(mongo, event_path, "api-1", app_log)
    event = {"event_id": "example", "event_type": "deposit", "outcome": "success"}
    sink.publish([("events_bronze", event)])
    if not file_down:
        assert json.loads(event_path.read_text())["event_type"] == "deposit"
    if not mongo_down:
        mongo.__getitem__.return_value.insert_one.assert_called_once()
    if mongo_down or file_down:
        [warning] = [json.loads(line) for line in app_log.path.read_text().splitlines()]
        assert warning["level"] == "WARNING"
        assert "secret" not in app_log.path.read_text()
        assert "event_type" not in warning
    else:
        assert not app_log.path.exists()
