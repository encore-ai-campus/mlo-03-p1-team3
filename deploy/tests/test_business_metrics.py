import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('business_metrics', Path(__file__).parents[1]/'ansible/files/business-metrics.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class BusinessSnapshotTests(unittest.TestCase):
    def test_successful_empty_database_has_explicit_zeros_and_freshness(self):
        with patch.object(m.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'card_payments\tall\t0\n', '')):
            rows = m.maria_snapshot()
        self.assertEqual(len(rows), 15)
        self.assertTrue(all(row.endswith(' 0.0') for row in rows))

    def test_collector_failure_removes_previous_counts_and_success_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'snapshot.prom'
            with patch.object(m, 'maria_snapshot', return_value=['podobank_db_records 12']):
                self.assertTrue(m.collect('mariadb', p, None))
            self.assertIn('success_timestamp_seconds', p.read_text())
            with patch.object(m, 'maria_snapshot', side_effect=ValueError('must never be exported')):
                self.assertFalse(m.collect('mariadb', p, None))
            text=p.read_text()
            self.assertNotIn('podobank_db_records', text)
            self.assertNotIn('success_timestamp_seconds', text)
            self.assertNotIn('must never', text)
            self.assertIn('podobank_business_collect_success{store="mariadb"} 0.0',text)
            self.assertFalse(p.with_suffix('.prom.tmp').exists())

    def test_maria_snapshot_is_read_only_and_rejects_unknown_labels(self):
        with patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'ledger_entries\tprivate-customer-value\t1\n','')) as run:
            with self.assertRaises(ValueError):m.maria_snapshot()
            sql=run.call_args.kwargs['input']
            self.assertIn('READ ONLY', sql)
            self.assertIn('max_statement_time=5',sql)
            for word in ('INSERT','UPDATE','DELETE','DROP'):self.assertNotIn(word,sql)

    def test_mongo_only_exports_known_collections_and_bounded_event_labels(self):
        result='{"collections":{"events_bronze":2,"card_payment_locations":0},"events":[{"event_type":"deposit","outcome":"success","count":1}]}'
        with patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0,result,'')):
            rows=m.mongo_snapshot(Path('fixed.js'))
        self.assertEqual(len(rows),16)
        self.assertIn('podobank_mongo_events{event_type="deposit",outcome="success"} 1.0',rows)
