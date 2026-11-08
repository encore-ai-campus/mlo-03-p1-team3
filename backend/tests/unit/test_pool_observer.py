import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

from app.observability.pool_observer import PoolObserver


def test_returned_connections_are_idle_and_still_open():
    engine = create_engine("sqlite://", poolclass=QueuePool, pool_size=2, max_overflow=0)
    observer = PoolObserver(engine)
    with engine.connect() as first, engine.connect() as second:
        first.execute(text("SELECT 1"))
        second.execute(text("SELECT 1"))
        assert observer.snapshot()["borrowed"] == 2
    state = observer.snapshot()
    assert state["borrowed"] == state["pool_checkedout"] == 0
    assert state["pool_idle"] == 2
    assert state["checkouts"] == state["checkins"] == 2
    assert state["created"] == 2 and state["closed"] == 0
    engine.dispose()


def test_exception_returns_borrowed_connection():
    engine = create_engine("sqlite://", poolclass=QueuePool)
    observer = PoolObserver(engine)
    with pytest.raises(RuntimeError), engine.begin():
        raise RuntimeError("probe")
    state = observer.snapshot()
    assert state["checkouts"] == state["checkins"] == 1
    assert state["borrowed"] == 0
    engine.dispose()
