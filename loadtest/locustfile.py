"""Podobank health 또는 로그인 조회. 금융 거래·회원 생성은 수행하지 않는다."""

import json
import os
import random
import time
from collections import Counter, deque
from datetime import UTC, datetime
from pathlib import Path

import gevent
from locust import HttpUser, between, events, task
from locust.exception import StopUser

from handoff_common import parse_accounts
from reporting import StageCSV

PROFILE = os.environ.get("PODOBANK_PROFILE", "health")
TARGET = int(os.environ.get("PODOBANK_TARGET_USERS", "1"))
ACCOUNTS = deque(parse_accounts(os.environ.get("PODOBANK_ACCOUNTS_JSON"), TARGET)
                 if PROFILE == "read" else [])
STATE = {"measuring": False, "completed": False, "reason": "not_started", "peak_users": 0, "ready_users": 0,
         "min_measured_users": TARGET, "codes": Counter()}


def utc_now():
    return datetime.now(UTC).isoformat()


def stop(environment, reason):
    if STATE.get("stopping"):
        return
    STATE["stopping"] = True
    STATE["reason"] = reason
    STATE["ended_at"] = utc_now()
    if STATE["measuring"]:
        STATE["measured_seconds"] = time.monotonic() - STATE["measurement_clock"]
        STATE["measuring"] = False
    gevent.spawn(environment.runner.quit)


@events.test_start.add_listener
def start_test(environment, **_kwargs):
    STATE["reason"] = "ramping"

    def watch():
        started = time.monotonic()
        deadline = float(os.environ.get("PODOBANK_RAMP_TIMEOUT", "60"))
        while not STATE.get("stopping"):
            count = environment.runner.user_count
            STATE["peak_users"] = max(count, STATE["peak_users"])
            if STATE["measuring"]:
                STATE["min_measured_users"] = min(count, STATE["min_measured_users"])
                if count < TARGET:
                    stop(environment, "user_count_dropped")
            elif not STATE.get("warming") and time.monotonic() - started > deadline:
                stop(environment, "ramp_timeout")
            gevent.sleep(0.1)

    gevent.spawn(watch)


@events.spawning_complete.add_listener
def spawned(user_count, **_kwargs):
    if user_count < TARGET or STATE.get("warming") or STATE.get("stopping"):
        return
    STATE["warming"] = True

    def measure():
        deadline = time.monotonic() + float(os.environ.get("PODOBANK_RAMP_TIMEOUT", "60"))
        while STATE["ready_users"] < TARGET and not STATE.get("stopping"):
            if time.monotonic() > deadline:
                stop(ENV, "authentication_ready_timeout")
                return
            gevent.sleep(0.1)
        gevent.sleep(float(os.environ.get("PODOBANK_WARMUP", "10")))
        if STATE.get("stopping"):
            return
        if ENV.runner.user_count < TARGET:
            stop(ENV, "user_count_dropped")
            return
        ENV.stats.reset_all()
        STATE["codes"].clear()
        STATE["measuring"] = True
        STATE["started_at"] = utc_now()
        STATE["measurement_clock"] = time.monotonic()
        STATE["min_measured_users"] = ENV.runner.user_count
        gevent.sleep(float(os.environ.get("PODOBANK_HOLD_SECONDS", "60")))
        if not STATE.get("stopping"):
            STATE["completed"] = True
            stop(ENV, "completed")

    gevent.spawn(measure)


@events.init.add_listener
def init_environment(environment, **_kwargs):
    global ENV
    ENV = environment
    if stage_path := os.environ.get("PODOBANK_STAGE_JSON"):
        environment.podobank_csv = StageCSV(environment, Path(stage_path).parent / "locust")


@events.request.add_listener
def record_status(response=None, **_kwargs):
    if STATE["measuring"]:
        code = getattr(response, "status_code", 0) or 0
        STATE["codes"][str(code)] += 1


@events.test_stop.add_listener
def save_stage(environment, **_kwargs):
    total = environment.stats.total
    row = {key: STATE.get(key) for key in ("completed", "reason", "peak_users",
           "min_measured_users", "started_at", "ended_at", "measured_seconds")}
    row.update(users=TARGET, requests=total.num_requests, failures=total.num_failures,
               rps=total.total_rps, p50_ms=total.get_response_time_percentile(0.50) or 0,
               p95_ms=total.get_response_time_percentile(0.95) or 0,
               p99_ms=total.get_response_time_percentile(0.99) or 0,
               http_status=dict(STATE["codes"]))
    Path(os.environ["PODOBANK_STAGE_JSON"]).write_text(
        json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")


@events.test_stop.add_listener
def finish_csv(environment, **_kwargs):
    if report := getattr(environment, "podobank_csv", None):
        report.finish()


class PodobankUser(HttpUser):
    wait_time = between(float(os.environ.get("PODOBANK_WAIT_MIN", "1")),
                        float(os.environ.get("PODOBANK_WAIT_MAX", "3")))

    def on_start(self):
        self.client.trust_env = False
        if PROFILE == "read":
            if not ACCOUNTS:
                stop(self.environment, "insufficient_accounts")
                raise StopUser
            account = ACCOUNTS.popleft()
            with self.client.post("/api/v1/auth/login", json=account,
                                  name="POST /api/v1/auth/login", catch_response=True,
                                  timeout=10) as response:
                if response.status_code != 200:
                    response.failure("시험 계정 로그인 실패")
                    stop(self.environment, "login_failed")
                    raise StopUser
            with self.client.get("/api/v1/auth/me", name="GET /api/v1/auth/me",
                                 catch_response=True, timeout=10) as response:
                if response.status_code != 200:
                    response.failure("로그인 세션 확인 실패")
                    stop(self.environment, "session_check_failed")
                    raise StopUser
        STATE["ready_users"] += 1

    @task
    def browse(self):
        if PROFILE == "health":
            path = "/api/v1/health"
        else:
            path = random.choices(  # noqa: S311 부하 시나리오 선택이며 보안 난수가 아님
                ["/api/v1/accounts/me", "/api/v1/accounts/me/ledger?limit=20&offset=0",
                 "/api/v1/auth/me"], weights=[4, 4, 2])[0]
        name = "GET " + path.split("?")[0]
        with self.client.get(path, name=name, catch_response=True, timeout=10) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")
                return
            try:
                body = response.json()
            except ValueError:
                response.failure("JSON 응답 아님")
                return
            if PROFILE == "health" and (not isinstance(body, dict)
                    or any(body.get(db) != "ok" for db in ("mariadb", "mongodb"))):
                response.failure("DB health 비정상")
