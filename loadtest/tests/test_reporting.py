import csv
import sys
import tempfile
import unittest
from pathlib import Path

import gevent
from locust.env import Environment

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reporting import StageCSV


class CSVShutdownTests(unittest.TestCase):
    def test_final_snapshot_is_complete_and_writer_stops_before_close(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = Environment()
            report = StageCSV(environment, Path(directory) / 'locust')
            gevent.sleep(0)
            environment.stats.log_request('GET', '/api/v1/health', 12, 31)
            environment.stats.log_request('GET', '/api/v1/health', 15, 31)
            report.finish()
            report.finish()
            gevent.sleep(0)
            self.assertTrue(report.greenlet.dead)
            self.assertTrue(report.writer.requests_csv_filehandle.closed)
            with (Path(directory) / 'locust_stats.csv').open() as stream:
                total = next(row for row in csv.DictReader(stream) if row['Name'] == 'Aggregated')
            self.assertEqual(int(total['Request Count']), 2)
            self.assertEqual(int(total['Failure Count']), 0)


if __name__ == '__main__':
    unittest.main()
