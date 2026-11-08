import ast
import sys
import unittest
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.core.time import kst_iso

from loadtest.history_seed import (
    TRANSFER_DAILY_LIMIT,
    TRANSFER_MAX_AMOUNT,
    period,
    plan_months,
    validate_safety,
)


def backend_event_tools():
    # Execute the actual pure backend functions without importing DB/FastAPI packages.
    path = Path(__file__).resolve().parents[2] / "backend/app/api/events/service.py"
    tree = ast.parse(path.read_text())
    names = {"_check_keys", "amount_band", "build_event"}
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in names
        or isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id == "FORBIDDEN_KEYS" for t in node.targets
        )
    ]
    scope = {"uuid": uuid, "kst_iso": kst_iso}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), scope)  # noqa: S102 - trusted repository source
    return SimpleNamespace(**{k: v for k, v in scope.items() if k != "__builtins__"})


EVENT_TOOLS = backend_event_tools()
FORBIDDEN_KEYS = EVENT_TOOLS.FORBIDDEN_KEYS


class HistorySeedTests(unittest.TestCase):
    def setUp(self):
        self.accounts = [
            {"id": i, "user_id": i, "balance": 30_000 if i % 10 == 9 else 30_000_000}
            for i in range(1, 21)
        ]
        self.now = datetime(2026, 11, 8, 12)

    def test_plan(self):
        batches = list(plan_months(self.accounts, 2, 20261108, self.now, EVENT_TOOLS))
        self.assertEqual(
            batches,
            list(plan_months(self.accounts, 2, 20261108, self.now, EVENT_TOOLS)),
        )
        start, end = period(2, self.now)
        balances, daily, pairs = Counter(), Counter(), defaultdict(list)
        rows = [r for b in batches for r in b["ledger"]]
        self.assertEqual(
            [r["created_at"] for r in rows], sorted(r["created_at"] for r in rows)
        )
        for row in rows:
            aid = row["account_id"]
            balances[aid] += row["amount"]
            self.assertEqual(balances[aid], row["balance_after"])
            self.assertGreaterEqual(balances[aid], 0)
            self.assertTrue(start <= row["created_at"] < end)
            if row["entry_type"].startswith("transfer_"):
                pairs[row["transaction_id"]].append(row)
            if row["entry_type"] == "transfer_out":
                self.assertLessEqual(-row["amount"], TRANSFER_MAX_AMOUNT)
                daily[aid, row["created_at"].date()] -= row["amount"]
        self.assertTrue(all(n <= TRANSFER_DAILY_LIMIT for n in daily.values()))
        for pair in pairs.values():
            self.assertEqual(len(pair), 2)
            self.assertEqual(sum(r["amount"] for r in pair), 0)
            self.assertEqual(
                {r["entry_type"] for r in pair}, {"transfer_out", "transfer_in"}
            )
            self.assertEqual(pair[0]["transaction_id"], pair[1]["transaction_id"])
            self.assertNotEqual(pair[0]["account_id"], pair[1]["account_id"])
        self.assertEqual(dict(balances), {a["id"]: a["balance"] for a in self.accounts})
        devices = defaultdict(set)
        event_counts = Counter()

        def check(value):
            if isinstance(value, dict):
                self.assertFalse(FORBIDDEN_KEYS.intersection(value))
                for inner in value.values():
                    check(inner)
            elif isinstance(value, list):
                for inner in value:
                    check(inner)

        for batch in batches:
            for session in batch["sessions"]:
                self.assertTrue(
                    start
                    <= session["created_at"]
                    < session["last_seen_at"]
                    <= session["ended_at"]
                    < end
                )
                self.assertIsNone(session["user_agent"])
                self.assertEqual(len(session["token_hash"]), 64)
                devices[session["user_id"]].add(session["device_id"])
            for event in batch["events"]:
                check(event)
                event_counts[event["event_type"]] += 1
                self.assertEqual(event["source"], "history_seed")
                self.assertEqual(event["instance"], "history_seed")
                at = datetime.fromisoformat(event["occurred_at"]).replace(tzinfo=None)
                self.assertTrue(start <= at < end)
        self.assertTrue(all(1 <= len(ds) <= 2 for ds in devices.values()))
        self.assertEqual(event_counts["transfer"], len(pairs))
        self.assertEqual(
            event_counts["login"], sum(len(b["sessions"]) for b in batches)
        )

    def test_safety(self):
        ledger = [
            {
                "account_id": a["id"],
                "entry_type": "deposit",
                "amount": a["balance"],
                "balance_after": a["balance"],
            }
            for a in self.accounts
        ]
        validate_safety(self.accounts, ledger, 0, 0)
        for rows, sessions, events in [
            (ledger + [ledger[0]], 0, 0),
            (ledger, 1, 0),
            (ledger, 0, 1),
            (ledger[1:], 0, 0),
        ]:
            with self.assertRaises(ValueError):
                validate_safety(self.accounts, rows, sessions, events)
        with self.assertRaises(ValueError):
            validate_safety([], [], 0, 0)

    def test_calendar(self):
        self.assertEqual(period(1, datetime(2024, 3, 31))[0], datetime(2024, 2, 29))
        self.assertEqual(
            period(12, self.now), (datetime(2025, 11, 8), datetime(2026, 11, 8))
        )


if __name__ == "__main__":
    unittest.main()
