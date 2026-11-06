"""Offline unit tests for the plan-only generator."""
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from persona_sim import (load_json, init_pool, build_daily_plan, validate_plan,
                         validate_config)


class PersonaPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_json(ROOT / "config" / "personas.json")
        cls.users = init_pool(cls.cfg)
        cls.day = date(2026, 11, 6)
        cls.plan, cls.summary = build_daily_plan(cls.users, cls.cfg, cls.day)

    def test_pool_size_unique_and_profile_fields(self):
        self.assertEqual(len(self.users), 600)
        self.assertEqual(len({u["sim_user_id"] for u in self.users}), 600)
        counts = Counter(u["persona_type"] for u in self.users)
        self.assertEqual(dict(counts), self.cfg["pool_sizes"])
        for u in self.users:
            self.assertNotIn(u["sim_user_id"], u["known_recipient_sim_ids"])
            self.assertTrue(u["primary_device_id"])
            self.assertIsNone(u["backend_user_id"])
            self.assertGreater(u["opening_balance_krw"], 0)

    def test_daily_distinct_users_and_persona_counts(self):
        self.assertEqual(self.summary["users_active"], 400)
        self.assertEqual(self.summary["active_by_persona"], self.cfg["daily_active"])
        self.assertEqual(len(set(r["sim_user_id"] for r in self.plan)), 400)

    def test_no_real_events_or_results_fabricated(self):
        for r in self.plan:
            self.assertEqual(r["execution_status"], "PLANNED")
            self.assertNotIn("event_id", r)
            self.assertNotIn("outcome", r)
            self.assertNotIn("collected_at", r)
            self.assertNotIn("password", str(r))

    def test_session_ordering_and_length(self):
        validate_plan(self.plan, self.cfg, self.day)
        sessions = defaultdict(list)
        for r in self.plan:
            sessions[r["session_key"]].append(r)
            self.assertTrue(r["planned_at"].endswith("+09:00"))
        for entries in sessions.values():
            ordered = sorted(entries, key=lambda x: x["planned_at"])
            self.assertEqual(ordered[0]["action"], "login")
            self.assertEqual(ordered[-1]["action"], "logout")
            self.assertLess(
                datetime.fromisoformat(ordered[-1]["planned_at"]) -
                datetime.fromisoformat(ordered[0]["planned_at"]),
                timedelta(minutes=60)
            )

    def test_p01_balance_history_link_and_balance_limits(self):
        per_user = defaultdict(list)
        for r in self.plan:
            if r["persona_type"] == "P01":
                per_user[r["sim_user_id"]].append(r)
        balance_participants = 0
        for rows in per_user.values():
            ordered = sorted(rows, key=lambda x: x["planned_at"])
            b = [r for r in ordered if r["action"] == "account_view"]
            h = [r for r in ordered if r["action"] == "history_view"]
            self.assertLessEqual(len(b), 3)
            self.assertLessEqual(len(h), 1)
            if b:
                balance_participants += 1
            if b and h:
                self.assertLess(datetime.fromisoformat(b[0]["planned_at"]),
                                datetime.fromisoformat(h[0]["planned_at"]))
        self.assertGreater(balance_participants, 90)
        self.assertLess(balance_participants, 140)

    def test_application_limit_and_valid_transfer(self):
        self.assertLessEqual(sum(r["action"] == "loan_apply" for r in self.plan), 6)
        self.assertEqual(self.summary["fds_candidate_users"], 4)
        pool_ids = {u["sim_user_id"] for u in self.users}
        for r in self.plan:
            if r["action"] == "transfer":
                self.assertIn(r["params"]["recipient_sim_user_id"], pool_ids)
                self.assertNotEqual(r["params"]["recipient_sim_user_id"], r["sim_user_id"])
                self.assertGreater(r["params"]["amount_krw"], 0)
                self.assertLessEqual(r["params"]["amount_krw"], 10000000)

    def test_seed_replay_and_next_day_change(self):
        again, second_summary = build_daily_plan(self.users, self.cfg, self.day)
        self.assertEqual(again, self.plan)
        self.assertEqual(second_summary, self.summary)
        other, other_summary = build_daily_plan(self.users, self.cfg, date(2026, 11, 7))
        self.assertEqual(other_summary["users_active"], 400)
        self.assertNotEqual([r["plan_id"] for r in self.plan],
                            [r["plan_id"] for r in other])
        self.assertEqual(self.users, init_pool(self.cfg))

    def test_invalid_configuration_rejected(self):
        import copy
        bad = copy.deepcopy(self.cfg)
        bad["daily_active"]["P01"] = 1000
        with self.assertRaises(ValueError):
            validate_config(bad)


if __name__ == "__main__":
    unittest.main()
