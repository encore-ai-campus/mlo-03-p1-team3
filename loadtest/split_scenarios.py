"""Isolate login RPS from transfer-flow TPS using Locust's HTTP statistics.

Accounts and credentials exist only in memory. No resets, financial retries,
user respawning, or login requests during a measured transfer phase.
"""

from gevent import monkey

monkey.patch_all()

import argparse
import json
import random
import re
import secrets
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import gevent
from gevent.pool import Group, Pool
from locust.clients import HttpSession
from locust.env import Environment

API = "/api/v1"


def now():
    return datetime.now(UTC).isoformat()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def error_classes(error):
    """Keep nested transport exception types, never raw URLs, bodies or headers."""
    found, seen = set(), set()

    def visit(value):
        if not isinstance(value, BaseException) or id(value) in seen:
            return
        seen.add(id(value))
        found.add(type(value).__name__)
        for child in [
            value.__cause__,
            value.__context__,
            getattr(value, "reason", None),
            *value.args,
        ]:
            visit(child)

    visit(error)
    return ",".join(sorted(found)) or "no_http_response"


@dataclass
class Account:
    index: int
    phone: str = field(repr=False)
    password: str = field(repr=False)
    client: object = field(repr=False)
    poor: bool = False
    initial: int = 0
    busy: bool = False


class Experiment:
    def __init__(self, host, count=1000, seed=20261107):
        self.env = Environment(host=host)
        self.runner = self.env.create_local_runner()
        prefix = secrets.randbelow(100_000)
        self.accounts = [
            Account(
                i,
                f"019{prefix:05d}{i:03d}",
                secrets.token_urlsafe(18),
                HttpSession(host, self.env.events.request, None),
                i % 10 == 9,
            )
            for i in range(count)
        ]
        for a in self.accounts:
            a.client.trust_env = False
        self.rng = random.Random(seed)
        self.delta = defaultdict(int)
        self.uncertain = set()
        self.ready = False
        self.auth_during_transfer = 0
        self.phase = "preparation"
        self.codes = Counter()
        self.transfer_attempts = 0
        self.cursor = 0

    def request(self, account, method, path, name, body=None, expected_poor=False):
        if self.phase.startswith("transfer") and path.startswith("/auth/"):
            self.auth_during_transfer += 1
            raise RuntimeError(
                "Authentication requests forbidden during transfer measurement"
            )
        kwargs = {
            "timeout": (3, 10),
            "name": name,
            "catch_response": True,
            "allow_redirects": False,
        }
        if body is not None:
            kwargs["json"] = body
        with account.client.request(method, API + path, **kwargs) as response:
            status = response.status_code
            try:
                data = response.json()
                if not isinstance(data, dict):
                    data = {}
            except ValueError:
                data = {}
            code = data.get("code", "")
            if not isinstance(code, str) or not re.fullmatch("[a-z_]*", code):
                code = "unrecognized_error"
            accepted = status == 200 or (
                expected_poor and status == 409 and code == "insufficient_funds"
            )
            if (
                status == 200
                and path == "/transfers"
                and (
                    not isinstance(data.get("balance"), int)
                    or not data.get("transaction_id")
                )
            ):
                accepted = False
                code = "invalid_transfer_response"
            if not accepted:
                detail = (
                    error_classes(getattr(response, "error", None))
                    if status == 0
                    else code or "unexpected_response"
                )
                self.codes[f"{name}:HTTP{status}:{detail}"] += 1
                response.failure(f"HTTP{status}:{detail}")
            elif status == 409:
                response.request_meta["name"] = name + "(잔액부족)"
                response.success()
            return status, data, accepted

    def login(self, account):
        return self.request(
            account,
            "POST",
            "/auth/login",
            "로그인",
            {"phone_number": account.phone, "password": account.password},
        )[2]

    def prepare(self, funded=False):
        def signup(a):
            body = {
                "name": f"LOAD-SPLIT-{a.index}",
                "phone_number": a.phone,
                "password": a.password,
                "birth_year": 1995,
                "gender": "male",
                "marital_status": "single",
                "is_employed": True,
            }
            if not self.request(a, "POST", "/auth/signup", "준비-가입", body)[2]:
                raise RuntimeError(
                    "Account preparation failed; see sanitized preparation errors"
                )
            if funded:
                a.initial = 30_000 if a.poor else 30_000_000
                remaining = a.initial
                while remaining:
                    amount = min(remaining, 10_000_000)
                    if not self.request(
                        a,
                        "POST",
                        "/transactions/deposit",
                        "준비-입금",
                        {"amount": amount},
                    )[2]:
                        raise RuntimeError("Funding preparation failed")
                    remaining -= amount
            if not self.request(a, "POST", "/auth/logout", "준비-로그아웃")[2]:
                raise RuntimeError("Preparation logout failed")
            a.client.close()
            a.client = HttpSession(self.env.host, self.env.events.request, None)
            a.client.trust_env = False

        for _ in Pool(8).imap_unordered(signup, self.accounts):
            pass

    def prelogin(self, rate):
        self.phase = "prelogin"
        successes = []
        pending = Group()
        started = time.monotonic()
        for i, a in enumerate(self.accounts):
            gevent.sleep(max(0, started + i / rate - time.monotonic()))
            pending.spawn(lambda account=a: successes.append(self.login(account)))
        pending.join(timeout=20)
        self.ready = (
            len(successes) == len(self.accounts) and all(successes) and not pending
        )
        if pending:
            pending.kill(block=True)
        return {
            "accounts": len(self.accounts),
            "successful": sum(successes),
            "ready": self.ready,
            "seconds": round(time.monotonic() - started, 2),
            "errors": dict(self.codes),
        }

    def flow(self, a):
        if not self.ready:
            raise RuntimeError("All sessions must be ready before transfers")
        if not self.request(a, "GET", "/accounts/me", "조회-잔액")[2]:
            return
        offset = self.rng.randrange(1, len(self.accounts))
        other = self.accounts[(a.index + offset) % len(self.accounts)]
        if not self.request(
            a,
            "POST",
            "/transfers/recipient-lookup",
            "조회-받는사람",
            {"query": other.phone},
        )[2]:
            return
        amount = self.rng.randrange(10_000, 100_001, 1_000)
        self.transfer_attempts += 1
        parties = (a.index, other.index)
        try:
            status, data, _accepted = self.request(
                a,
                "POST",
                "/transfers",
                "송금",
                {"recipient": other.phone, "amount": amount},
                expected_poor=a.poor,
            )
            if (
                status == 200
                and isinstance(data.get("balance"), int)
                and data.get("transaction_id")
            ):
                self.delta[a.index] -= amount
                self.delta[other.index] += amount
            elif status == 0 or status >= 500 or status == 200:
                self.uncertain.update(parties)
        except BaseException:
            self.uncertain.update(parties)
            raise
        self.request(a, "GET", "/accounts/me", "조회-잔액")

    def stage(self, mode, rate, seconds):
        if mode == "transfer" and not self.ready:
            raise RuntimeError(
                "Cannot measure transfers before successful prelogin barrier"
            )
        self.phase = mode
        self.env.stats.reset_all()
        self.codes.clear()
        self.transfer_attempts = 0
        pending, exceptions = Group(), []
        scheduled = missed = completed = 0
        started, stamp = time.monotonic(), now()
        slots = round(rate * seconds)

        def work(a):
            nonlocal completed
            try:
                self.login(a) if mode == "login" else self.flow(a)
                completed += 1
            except Exception as exc:  # noqa: BLE001 - record worker failure without leaking request data
                exceptions.append(type(exc).__name__)
            finally:
                a.busy = False

        for slot in range(slots):
            deadline = started + slot / rate
            gevent.sleep(max(0, deadline - time.monotonic()))
            a = self.accounts[self.cursor % len(self.accounts)]
            self.cursor += 1
            if time.monotonic() - deadline > max(0.1, 2 / rate) or a.busy:
                missed += 1
                continue
            a.busy = True
            scheduled += 1
            pending.spawn(work, a)
        gevent.sleep(max(0, started + seconds - time.monotonic()))
        window_end = now()
        pending.join(timeout=60)
        undrained = len(pending)
        if pending:
            pending.kill(block=True)
        elapsed = time.monotonic() - started
        total = self.env.stats.total
        rows = [
            {
                "name": s.name,
                "method": s.method,
                "requests": s.num_requests,
                "failures": s.num_failures,
                "p50_ms": s.get_response_time_percentile(0.5),
                "p95_ms": s.get_response_time_percentile(0.95),
                "p99_ms": s.get_response_time_percentile(0.99),
            }
            for s in self.env.stats.entries.values()
            if s.num_requests
        ]
        return {
            "mode": mode,
            "target_rate": rate,
            "accounts": len(self.accounts),
            "start": stamp,
            "window_end": window_end,
            "drained_end": now(),
            "window_seconds": seconds,
            "elapsed_with_drain": round(elapsed, 3),
            "scheduled": scheduled,
            "missed_schedule": missed,
            "completed": completed,
            "undrained": undrained,
            "transfer_attempts": self.transfer_attempts,
            "transfer_tps": self.transfer_attempts / seconds,
            "requests": total.num_requests,
            "failures": total.num_failures,
            "fail_ratio": total.fail_ratio,
            "rps": total.num_requests / seconds,
            "p50_ms": total.get_response_time_percentile(0.5),
            "p95_ms": total.get_response_time_percentile(0.95),
            "p99_ms": total.get_response_time_percentile(0.99),
            "errors": dict(self.codes),
            "worker_exceptions": dict(Counter(exceptions)),
            "by_name": rows,
            "auth_during_transfer": self.auth_during_transfer,
            "loadgen_cpu_warning": bool(self.runner.cpu_warning_emitted),
        }

    def verify_balances(self):
        self.phase = "verification"
        result = Counter()
        differences = []

        def one(a):
            _status, data, ok = self.request(a, "GET", "/accounts/me", "검증-잔액")
            if not ok or not isinstance(data.get("balance"), int):
                result["errors"] += 1
                return
            if a.index in self.uncertain:
                result["uncertain"] += 1
                return
            result["checked"] += 1
            if data["balance"] != a.initial + self.delta[a.index]:
                result["mismatched"] += 1
                differences.append(data["balance"] - (a.initial + self.delta[a.index]))

        for _ in Pool(8).imap_unordered(one, self.accounts):
            pass
        return {
            k: result[k] for k in ["checked", "uncertain", "mismatched", "errors"]
        } | {"total_diff": sum(differences)}

    def close(self):
        for a in self.accounts:
            a.client.close()
        self.runner.quit()


def evaluate(row, max_fail=0.01, max_p95=500):
    reasons = []
    if row["requests"] == 0:
        reasons.append("no_requests")
    if row["fail_ratio"] > max_fail:
        reasons.append("failure_ratio")
    if row["p95_ms"] is None or row["p95_ms"] > max_p95:
        reasons.append("latency")
    if row["missed_schedule"] or row["undrained"] or row["worker_exceptions"]:
        reasons.append("invalid_load_delivery")
    if row["auth_during_transfer"]:
        reasons.append("authentication_mixed_into_transfers")
    if any("HTTP401" in k for k in row["errors"]):
        reasons.append("session_or_authentication_failure")
    if row["mode"] == "transfer" and row["transfer_tps"] < row["target_rate"] * 0.95:
        reasons.append("target_transfer_tps_not_reached")
    if row["loadgen_cpu_warning"]:
        reasons.append("load_generator_cpu_warning")
    return not reasons, reasons


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["login", "transfer"])
    p.add_argument("--host", required=True)
    p.add_argument("--allow-remote", action="store_true")
    p.add_argument("--accounts", type=int, default=1000)
    p.add_argument("--rates", default=None)
    p.add_argument("--seconds", type=float, default=60)
    p.add_argument("--warmup", type=float, default=10)
    p.add_argument("--cooldown", type=float, default=10)
    p.add_argument("--prelogin-rate", type=float, default=5)
    p.add_argument("--output", type=Path, default=Path("loadtest/results"))
    args = p.parse_args()
    origin = urlsplit(args.host)
    if (
        origin.scheme not in ["http", "https"]
        or not origin.hostname
        or origin.username
        or origin.password
        or origin.query
        or origin.fragment
        or origin.path not in ["", "/"]
    ):
        p.error("host must be an HTTP origin without credentials, query or path")
    if (
        origin.hostname not in ["localhost", "127.0.0.1", "::1"]
        and not args.allow_remote
    ):
        p.error("explicit --allow-remote required")
    rates = [
        float(x)
        for x in (
            args.rates
            or ("1,2,5,10,20" if args.mode == "login" else "10,20,40,80,160,320")
        ).split(",")
    ]
    if (
        not 2 <= args.accounts <= 1000
        or min(rates) <= 0
        or args.seconds <= 0
        or min(args.warmup, args.cooldown) < 0
        or args.prelogin_rate <= 0
    ):
        p.error("invalid account count, rates or durations")
    folder = args.output / (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + args.mode
    )
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {
        "mode": args.mode,
        "host": args.host,
        "accounts": args.accounts,
        "rates": rates,
        "started": now(),
        "conditions": {
            "seconds": args.seconds,
            "warmup": args.warmup,
            "cooldown": args.cooldown,
            "prelogin_rate": args.prelogin_rate,
            "financial_retries": 0,
            "database_reset": False,
            "transfer_flow": ["balance", "recipient_lookup", "transfer", "balance"],
        },
        "stages": [],
    }
    experiment = Experiment(args.host, args.accounts)
    try:
        print("Preparing", args.accounts, "accounts for", args.mode, flush=True)
        experiment.prepare(funded=args.mode == "transfer")
        manifest["prepared"] = now()
        write(folder / "manifest.json", manifest)
        if args.mode == "transfer":
            print(
                "Prelogin barrier: no transfer requests until every session is ready",
                flush=True,
            )
            experiment.codes.clear()
            manifest["prelogin"] = experiment.prelogin(args.prelogin_rate)
            write(folder / "manifest.json", manifest)
            if not experiment.ready:
                raise RuntimeError(
                    "Prelogin barrier failed; no transfer measurement started"
                )
            print("All sessions ready", flush=True)
            gevent.sleep(10)
        for rate in rates:
            print("Warmup", args.mode, rate, flush=True)
            warmup = (
                experiment.stage(args.mode, rate, args.warmup) if args.warmup else None
            )
            if warmup:
                write(folder / f"warmup-{rate:g}.json", warmup)
            row = experiment.stage(args.mode, rate, args.seconds)
            row["passed"], row["reasons"] = evaluate(row)
            manifest["stages"].append(row)
            write(folder / f"stage-{rate:g}.json", row)
            write(folder / "manifest.json", manifest)
            print(
                json.dumps(
                    {
                        k: row[k]
                        for k in [
                            "mode",
                            "target_rate",
                            "requests",
                            "failures",
                            "p95_ms",
                            "transfer_tps",
                            "passed",
                            "reasons",
                        ]
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if not row["passed"]:
                break
            gevent.sleep(args.cooldown)
        if args.mode == "transfer":
            manifest["balances"] = experiment.verify_balances()
    except Exception as exc:  # noqa: BLE001 - record worker failure without leaking request data
        manifest["execution_error"] = type(exc).__name__
        manifest["preparation_errors"] = dict(experiment.codes)
        print(
            "Stopped:",
            type(exc).__name__,
            "(sanitized details in manifest)",
            flush=True,
        )
    finally:
        manifest["finished"] = now()
        write(folder / "manifest.json", manifest)
        experiment.close()
    passed = (
        bool(manifest["stages"])
        and all(r["passed"] for r in manifest["stages"])
        and not manifest.get("execution_error")
    )
    if args.mode == "transfer" and manifest.get("balances"):
        passed = (
            passed
            and not manifest["balances"]["mismatched"]
            and not manifest["balances"]["errors"]
        )
    print("Results:", folder, flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
