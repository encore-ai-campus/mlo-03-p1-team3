"""Pool persistence must survive restarts without leaking or duplicating money."""

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reusable_pool_store import PoolError, PoolStore


class AccountPoolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / ".env"
        self.host = "http://127.0.0.1:8000"

    def tearDown(self):
        self.tmp.cleanup()

    def test_ten_thousand_accounts_have_unique_valid_phones_and_private_storage(self):
        with PoolStore(self.path, self.host) as pool:
            pool.create(10000)
            phones = [a["phone_number"] for a in pool.accounts]
            self.assertEqual(len(set(phones)), 10000)
            self.assertTrue(all(len(p) == 11 and p.startswith("019") for p in phones))
            self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
            self.assertNotIn(pool.accounts[0]["password"], repr(pool))
        with PoolStore(self.path, self.host) as pool:
            self.assertEqual(len(pool.accounts), 10000)
            self.assertEqual(pool.accounts[-1]["state"], "new")

    def test_reopen_preserves_confirmed_and_uncertain_progress(self):
        with PoolStore(self.path, self.host) as pool:
            pool.create(2)
            password = pool.accounts[0]["password"]
            pool.update(0, state="funding", funded=10000000)
            pool.update(1, state="ready", funded=30000)
        with PoolStore(self.path, self.host) as pool:
            self.assertEqual(pool.accounts[0]["password"], password)
            self.assertEqual(pool.accounts[0]["state"], "funding")
            self.assertEqual(pool.accounts[0]["funded"], 10000000)
            with self.assertRaises(PoolError):
                pool.select(2)

    def test_selection_requires_ready_accounts_and_never_silently_creates(self):
        with PoolStore(self.path, self.host) as pool:
            with self.assertRaises(PoolError):
                pool.select(2)
            pool.create(3)
            for i in range(2):
                pool.update(i, state="ready", funded=30000000)
            self.assertEqual(len(pool.select(2)), 2)
            with self.assertRaises(PoolError):
                pool.select(3)
            with self.assertRaises(PoolError):
                pool.select(4)

    def test_different_host_and_shared_permissions_fail_without_exposing_content(self):
        with PoolStore(self.path, self.host) as pool:
            pool.create(2)
            password = pool.accounts[0]["password"]
        with self.assertRaises(PoolError) as ctx, PoolStore(self.path, "http://other.invalid"):
            pass
        self.assertNotIn(password, str(ctx.exception))
        os.chmod(self.path, 0o644)
        with self.assertRaises(PoolError), PoolStore(self.path, self.host):
            pass

    def test_second_runner_cannot_use_locked_pool(self):
        with PoolStore(self.path, self.host) as pool:
            pool.create(2)
            with self.assertRaises(PoolError), PoolStore(self.path, self.host):
                pass

    def test_symlink_and_non_env_destination_are_rejected(self):
        outside = Path(self.tmp.name) / "outside"
        outside.write_text("do not overwrite")
        self.path.symlink_to(outside)
        with self.assertRaises(PoolError), PoolStore(self.path, self.host):
            pass
        self.assertEqual(outside.read_text(), "do not overwrite")
        with self.assertRaises(PoolError), PoolStore(Path(self.tmp.name) / "pool.json", self.host):
            pass

    def test_corrupt_records_and_duplicate_phones_are_rejected_safely(self):
        with PoolStore(self.path, self.host) as pool:
            pool.create(2)
            duplicate = dict(pool.accounts[1], phone_number=pool.accounts[0]["phone_number"])
        with self.path.open("a") as stream:
            stream.write("PODOBANK_TRANSFER_ACCOUNT_00001=" + json.dumps(duplicate) + "\n")
        with self.assertRaises(PoolError), PoolStore(self.path, self.host):
            pass

    def test_incomplete_last_write_is_discarded_before_resuming(self):
        with PoolStore(self.path, self.host) as pool:
            pool.create(2)
            pool.update(0, state="funding")
        with self.path.open("a") as stream:
            stream.write('PODOBANK_TRANSFER_ACCOUNT_00000={"password":"partial')
        with PoolStore(self.path, self.host) as pool:
            self.assertEqual(pool.accounts[0]["state"], "funding")
            pool.update(1, state="ready", funded=30000)
        with PoolStore(self.path, self.host) as pool:
            self.assertEqual(pool.accounts[1]["state"], "ready")

    def test_rejected_foreign_env_is_never_truncated(self):
        content = "UNRELATED_KEY=keep-this-value"
        self.path.write_text(content)
        os.chmod(self.path, 0o600)
        with self.assertRaises(PoolError), PoolStore(self.path, self.host):
            pass
        self.assertEqual(self.path.read_text(), content)


if __name__ == "__main__":
    unittest.main()
