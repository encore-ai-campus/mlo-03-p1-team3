"""Exercise pool preparation and reuse through a real local HTTP server."""

import io
import json
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gevent.pywsgi import WSGIServer
from reusable_pool_store import PoolError, PoolStore
from split_scenarios import Experiment, main, prepare_pool


class PoolPreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / ".env"
        self.paths, self.balances, self.passwords = [], {}, {}
        self.fail_deposit = False
        self.idle_seconds = None
        self.last_seen = {}

        def app(environ, start):
            path = environ["PATH_INFO"].removeprefix("/api/v1")
            self.paths.append(path)
            body = json.loads(environ["wsgi.input"].read(int(environ.get("CONTENT_LENGTH") or 0)) or b"{}")
            cookie = environ.get("HTTP_COOKIE", "")
            phone = cookie.partition("pool_phone=")[2].split(";", 1)[0]
            status, data, headers = "200 OK", {}, []
            if path in ("/auth/signup", "/auth/login"):
                phone = body["phone_number"]
                if path.endswith("signup"):
                    if phone in self.balances:
                        status, data = "409 Conflict", {"code": "phone_exists"}
                    else:
                        self.balances[phone] = 0
                        self.passwords[phone] = body["password"]
                elif self.passwords.get(phone) != body["password"]:
                    status, data = "401 Unauthorized", {"code": "invalid_credentials"}
                headers.append(("Set-Cookie", "pool_phone=" + phone + "; Path=/"))
                if status == "200 OK":
                    self.last_seen[phone] = time.monotonic()
            elif path == "/accounts/me":
                if self.idle_seconds is not None and time.monotonic() - self.last_seen.get(phone, 0) >= self.idle_seconds:
                    status, data = "401 Unauthorized", {"code": "authentication_required"}
                else:
                    self.last_seen[phone] = time.monotonic()
                    data = {"balance": self.balances[phone]}
            elif path == "/transactions/deposit":
                self.balances[phone] += body["amount"]
                data = {"balance": self.balances[phone], "transaction_id": "deposit-id"}
                if self.fail_deposit:
                    status, data = "503 Unavailable", {"code": "database_unavailable"}
            elif path == "/transfers":
                amount = body["amount"]
                self.balances[phone] -= amount
                self.balances[body["recipient"]] += amount
                data = {"balance": self.balances[phone], "transaction_id": "transfer-id"}
            raw = json.dumps(data).encode()
            start(status, headers + [("Content-Type", "application/json"), ("Content-Length", str(len(raw)))])
            return [raw]

        self.server = WSGIServer(("127.0.0.1", 0), app, log=None)
        self.server.start()
        self.host = "http://127.0.0.1:" + str(self.server.server_port)

    def tearDown(self):
        self.server.stop()
        self.tmp.cleanup()

    def test_prepare_is_reusable_without_signup_or_deposit_on_second_run(self):
        with PoolStore(self.path, self.host) as pool:
            pool.create(2)
            exp = Experiment(self.host, count=2, records=pool.accounts)
            try:
                result = prepare_pool(exp, pool)
                self.assertEqual(result["ready"], 2)
                self.assertEqual(sorted(self.balances.values()), [30000000, 30000000])
                self.paths.clear()
                result = prepare_pool(exp, pool)
                self.assertEqual(result["ready"], 2)
                self.assertEqual(self.paths, [])
            finally:
                exp.close()

    def test_uncertain_deposit_is_not_repeated_after_restart(self):
        self.fail_deposit = True
        with PoolStore(self.path, self.host) as pool:
            pool.create(2)
            exp = Experiment(self.host, count=2, records=pool.accounts)
            try:
                with self.assertRaises(PoolError):
                    prepare_pool(exp, pool)
            finally:
                exp.close()
        self.paths.clear()
        with PoolStore(self.path, self.host) as pool:
            self.assertTrue(any(a["state"] == "funding" for a in pool.accounts))
            exp = Experiment(self.host, count=2, records=pool.accounts)
            try:
                with self.assertRaises(PoolError):
                    prepare_pool(exp, pool)
                self.assertNotIn("/transactions/deposit", self.paths)
            finally:
                exp.close()

    def test_interrupted_signup_recovers_using_saved_credentials(self):
        with PoolStore(self.path, self.host) as pool:
            pool.create(2)
            first = pool.accounts[0]
            self.balances[first["phone_number"]] = 0
            self.passwords[first["phone_number"]] = first["password"]
            pool.update(0, state="signup")
            exp = Experiment(self.host, count=2, records=pool.accounts)
            try:
                self.assertEqual(prepare_pool(exp, pool)["ready"], 2)
                self.assertEqual(self.paths.count("/auth/signup"), 1)
            finally:
                exp.close()

    def test_interruption_before_signup_request_can_resume(self):
        with PoolStore(self.path, self.host) as pool:
            pool.create(2)
            pool.update(0, state="signup")
            exp = Experiment(self.host, count=2, records=pool.accounts)
            try:
                self.assertEqual(prepare_pool(exp, pool)["ready"], 2)
                self.assertEqual(len(self.balances), 2)
            finally:
                exp.close()

    def test_signup_recovery_never_funds_an_existing_account_with_other_password(self):
        with PoolStore(self.path, self.host) as pool:
            pool.create(2)
            pool.update(0, state="signup")
            pool.update(1, state="ready", funded=30000000)
            phone = pool.accounts[0]["phone_number"]
            self.balances[phone], self.passwords[phone] = 7000000, "another-private-password"
            exp = Experiment(self.host, count=2, records=pool.accounts)
            try:
                with self.assertRaises(PoolError):
                    prepare_pool(exp, pool)
                self.assertEqual(self.balances[phone], 7000000)
                self.assertNotIn("/transactions/deposit", self.paths)
            finally:
                exp.close()

    def test_slow_prelogin_preserves_sessions_and_keeper_stops_before_measurement(self):
        self.idle_seconds = 0.08
        with PoolStore(self.path, self.host) as pool:
            pool.create(3)
            for i, a in enumerate(pool.accounts):
                pool.update(i, state="ready", funded=30000000)
                self.balances[a["phone_number"]] = 30000000
                self.passwords[a["phone_number"]] = a["password"]
            exp = Experiment(self.host, count=3, records=pool.select(3))
            try:
                result = exp.prelogin(10, keepalive_interval=0.02)
                self.assertTrue(result["ready"])
                self.assertGreater(result["keepalive_requests"], 0)
                exp.capture_balances()
                row = exp.stage("transfer", 10, 0.1)
                self.assertEqual(row["requests"], 4)
                self.assertEqual(row["auth_during_transfer"], 0)
            finally:
                exp.close()

    def test_reuse_uses_current_balances_and_sends_no_signup_or_funding(self):
        with PoolStore(self.path, self.host) as pool:
            pool.create(3)
            for i, a in enumerate(pool.accounts):
                pool.update(i, state="ready", funded=30000000)
                self.balances[a["phone_number"]] = 7000000 + i * 1000000
                self.passwords[a["phone_number"]] = a["password"]
            exp = Experiment(self.host, count=2, records=pool.select(2))
            try:
                self.assertTrue(exp.prelogin(1000)["ready"])
                exp.capture_balances()
                self.assertEqual([a.initial for a in exp.accounts], [7000000, 8000000])
                row = exp.stage("transfer", 10, 0.1)
                self.assertEqual(row["requests"], 4)
                self.assertEqual(row["auth_during_transfer"], 0)
                self.assertEqual(exp.verify_balances()["mismatched"], 0)
                self.assertNotIn("/auth/signup", self.paths)
                self.assertNotIn("/transactions/deposit", self.paths)
            finally:
                exp.close()

    def test_cli_prepares_once_then_runs_twice_without_creating_accounts(self):
        common = ["--host", self.host, "--accounts", "2", "--pool-env", str(self.path),
                  "--output", str(Path(self.tmp.name) / "results")]
        out = io.StringIO()
        with redirect_stdout(out):
            with patch.object(sys, "argv", ["split_scenarios.py", "prepare-pool", *common]):
                self.assertEqual(main(), 0)
            self.paths.clear()
            for _ in range(2):
                with patch.object(sys, "argv", ["split_scenarios.py", "transfer", *common,
                     "--rates", "10", "--warmup", "0", "--seconds", "0.1",
                     "--cooldown", "0", "--prelogin-rate", "1000"]):
                    self.assertEqual(main(), 0)
        self.assertEqual(len(self.balances), 2)
        self.assertNotIn("/auth/signup", self.paths)
        self.assertNotIn("/transactions/deposit", self.paths)
        artifacts = out.getvalue() + "".join(p.read_text() for p in Path(self.tmp.name).rglob("*.json"))
        for password in self.passwords.values():
            self.assertNotIn(password, artifacts)

    def test_upstream_flat_pool_format_is_reused_without_preparation(self):
        records = [
            {"phone_number": "01900000001", "password": "fixture-password"},
            {"phone_number": "01900000002", "password": "fixture-password"},
        ]
        self.path.write_text("PODOBANK_ACCOUNTS_JSON=" + json.dumps(records) + "\n")
        for record in records:
            self.balances[record["phone_number"]] = 30000000
            self.passwords[record["phone_number"]] = record["password"]
        with redirect_stdout(io.StringIO()), patch.object(sys, "argv", [
            "split_scenarios.py", "transfer", "--host", self.host,
            "--accounts", "2", "--pool-env", str(self.path),
            "--output", str(Path(self.tmp.name) / "flat-results"),
            "--rates", "10", "--warmup", "0", "--seconds", "0.1",
            "--cooldown", "0", "--prelogin-rate", "1000",
        ]):
            self.assertEqual(main(), 0)
        self.assertNotIn("/auth/signup", self.paths)
        self.assertNotIn("/transactions/deposit", self.paths)
        [manifest] = Path(self.tmp.name).glob("flat-results/*/manifest.json")
        self.assertEqual(json.loads(manifest.read_text())["balances"]["mismatched"], 0)


if __name__ == "__main__":
    unittest.main()
