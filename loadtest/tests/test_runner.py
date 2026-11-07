"""Regression checks for false passes and safe resumption before live load."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from handoff_common import evaluate_stage, parse_accounts, resume_stages, validate_origin


class StageDecisionTests(unittest.TestCase):
    def evaluate(self, **changes):
        row = dict(users=20, min_measured_users=20, process_exit=0, completed=True,
                   measured_seconds=60, requests=600, failures=0, p95_ms=30)
        return evaluate_stage(row | changes, seconds=60, max_fail_ratio=0.01, max_p95_ms=500)[0]

    def test_healthy_stage_passes(self):
        self.assertTrue(self.evaluate())

    def test_fast_but_incomplete_stage_does_not_pass(self):
        for changes in [dict(measured_seconds=15), dict(min_measured_users=19),
                        dict(completed=False), dict(requests=0), dict(process_exit=1)]:
            with self.subTest(changes=changes):
                self.assertFalse(self.evaluate(**changes))

    def test_error_and_latency_limits_stop_escalation(self):
        self.assertTrue(self.evaluate(failures=6, p95_ms=500))
        self.assertFalse(self.evaluate(failures=7))
        self.assertFalse(self.evaluate(p95_ms=501))

    def test_resume_rechecks_three_prior_stages(self):
        stages = [5, 20, 50, 100, 200, 400]
        rows = [dict(users=n, passed=n != 400) for n in stages]
        self.assertEqual(resume_stages(stages, rows), [50, 100, 200, 400])

    def test_read_requires_distinct_accounts_and_origin_has_no_credentials(self):
        with self.assertRaises(ValueError):
            parse_accounts('[]', 1)
        for origin in ['http://example.test/api', 'http://example.test?token=dummy',
                       'http://dummy:dummy@example.test']:
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                validate_origin(origin)


if __name__ == '__main__':
    unittest.main()
