"""Observe pool ownership without logging queries, connection IDs or credentials."""
import threading
import time

from sqlalchemy import event


class PoolObserver:
    def __init__(self, engine):
        self.pool = engine.pool
        self.lock = threading.Lock()
        self.borrowed = 0
        self.borrowed_max = 0
        self.checkouts = 0
        self.checkins = 0
        self.created = 0
        self.closed = 0
        self.hold_max_ms = 0.0
        event.listen(engine, "checkout", self.checkout)
        event.listen(engine, "checkin", self.checkin)
        event.listen(engine, "connect", self.connect)
        event.listen(engine, "close", self.close)

    def checkout(self, connection, record, proxy):
        with self.lock:
            record.info["pool_observer_start"] = time.monotonic()
            self.borrowed += 1
            self.checkouts += 1
            self.borrowed_max = max(self.borrowed_max, self.borrowed)

    def checkin(self, connection, record):
        with self.lock:
            started = record.info.pop("pool_observer_start", None)
            if started is not None:
                self.borrowed -= 1
                self.checkins += 1
                self.hold_max_ms = max(self.hold_max_ms, (time.monotonic() - started) * 1000)

    def connect(self, connection, record):
        with self.lock:
            self.created += 1

    def close(self, connection, record):
        with self.lock:
            self.closed += 1

    def snapshot(self):
        with self.lock:
            return {
                "borrowed": self.borrowed, "borrowed_max": self.borrowed_max,
                "checkouts": self.checkouts, "checkins": self.checkins,
                "created": self.created, "closed": self.closed,
                "hold_max_ms": round(self.hold_max_ms, 3),
                "pool_idle": self.pool.checkedin(), "pool_checkedout": self.pool.checkedout(),
                "pool_size": self.pool.size(),
            }
