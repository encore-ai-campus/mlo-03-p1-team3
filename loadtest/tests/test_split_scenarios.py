"""Exercise real local HTTP requests: phase isolation and ambiguous money outcomes."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gevent.pywsgi import WSGIServer
from split_scenarios import Experiment, error_classes, evaluate


class SplitScenariosTests(unittest.TestCase):
    def setUp(self):
        self.paths = []
        self.login_ok = True
        self.money_status = "200 OK"

        def app(environ, start):
            path = environ["PATH_INFO"]
            self.paths.append(path)
            size = int(environ.get("CONTENT_LENGTH") or 0)
            if size:
                environ["wsgi.input"].read(size)
            status = "200 OK"
            data = {"balance": 100, "transaction_id": "test-transaction"}
            if path.endswith("/auth/login") and not self.login_ok:
                status = "503 Service Unavailable"
                data = {"code": "database_unavailable"}
            if path.endswith("/transfers"):
                status = self.money_status
                if status.startswith("503"):
                    data = {"code": "database_unavailable"}
            raw = json.dumps(data).encode()
            start(
                status,
                [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(raw))),
                ],
            )
            return [raw]

        self.server = WSGIServer(("127.0.0.1", 0), app, log=None)
        self.server.start()
        self.experiment = Experiment(
            "http://127.0.0.1:" + str(self.server.server_port), count=2
        )

    def tearDown(self):
        self.experiment.close()
        self.server.stop()

    def test_login_sends_only_authentication(self):
        row = self.experiment.stage("login", 20, 0.1)
        self.assertEqual(row["requests"], 2)
        self.assertEqual(set(self.paths), {"/api/v1/auth/login"})
        self.assertEqual(row["transfer_attempts"], 0)

    def test_failed_prelogin_cannot_start_any_financial_work(self):
        self.login_ok = False
        result = self.experiment.prelogin(1000)
        self.assertFalse(result["ready"])
        with self.assertRaises(RuntimeError):
            self.experiment.stage("transfer", 10, 0.1)
        self.assertFalse(any(p.endswith("/transfers") for p in self.paths))

    def test_transfer_flow_never_logs_in_and_tracks_both_sides(self):
        self.assertTrue(self.experiment.prelogin(1000)["ready"])
        self.paths.clear()
        row = self.experiment.stage("transfer", 10, 0.1)
        self.assertEqual(row["requests"], 4)
        self.assertEqual(row["transfer_attempts"], 1)
        self.assertEqual(sum(self.experiment.delta.values()), 0)
        self.assertEqual(row["auth_during_transfer"], 0)
        self.assertFalse(any("/auth/" in p for p in self.paths))

    def test_ambiguous_transfer_is_not_retried_and_marks_both_accounts(self):
        self.experiment.ready = True
        self.money_status = "503 Service Unavailable"
        row = self.experiment.stage("transfer", 10, 0.1)
        self.assertEqual(self.paths.count("/api/v1/transfers"), 1)
        self.assertEqual(self.experiment.uncertain, {0, 1})
        self.assertFalse(evaluate(row)[0])

    def test_transport_error_records_types_without_private_exception_text(self):
        error = ConnectionError("private-secret-value")
        error.__cause__ = TimeoutError("private-cookie-value")
        self.assertEqual(error_classes(error), "ConnectionError,TimeoutError")


if __name__ == "__main__":
    unittest.main()
