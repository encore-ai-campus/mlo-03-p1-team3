import pymysql
import pytest
from sqlalchemy.exc import OperationalError

from app.db.mariadb import with_deadlock_retry


def deadlock() -> OperationalError:
    return OperationalError("UPDATE", {}, pymysql.err.OperationalError(1213, "Deadlock found"))


def test_retries_once_on_deadlock():
    calls = []

    def fn():
        calls.append(1)
        if len(calls) == 1:
            raise deadlock()
        return "ok"

    assert with_deadlock_retry(fn) == "ok"
    assert len(calls) == 2


def test_gives_up_after_second_deadlock():
    def fn():
        raise deadlock()

    with pytest.raises(OperationalError):
        with_deadlock_retry(fn)
