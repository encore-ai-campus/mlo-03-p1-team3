"""Own the periodic CSV writer so it stops before files close and final totals flush."""
import gevent
from locust.stats import PERCENTILES_TO_REPORT, StatsCSVFileWriter


class StageCSV:
    def __init__(self, environment, prefix):
        self.writer = StatsCSVFileWriter(environment, PERCENTILES_TO_REPORT, str(prefix), full_history=True)
        self.greenlet = gevent.spawn(self.writer.stats_writer)
        self.closed = False

    def finish(self):
        if self.closed:
            return
        # Locust 2.47.0's CLI closes CSV handles without stopping its writer greenlet.
        # Stop our greenlet first, then overwrite the snapshot with the final totals.
        self.greenlet.kill(block=True)
        writer = self.writer
        try:
            for handle, csv_writer, render in [
                (writer.requests_csv_filehandle, writer.requests_csv_writer, writer.requests_csv),
                (writer.failures_csv_filehandle, writer.failures_csv_writer, writer.failures_csv),
                (writer.exceptions_csv_filehandle, writer.exceptions_csv_writer, writer.exceptions_csv),
            ]:
                handle.seek(0)
                render(csv_writer)
                handle.truncate()
                handle.flush()
        finally:
            writer.close_files()
            self.closed = True
