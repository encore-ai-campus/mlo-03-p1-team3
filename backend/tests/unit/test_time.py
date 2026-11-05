from datetime import datetime

from app.core.time import kst_day_range_utc


def test_kst_day_range_after_kst_midnight():
    start, end = kst_day_range_utc(datetime(2026, 11, 2, 15, 30))

    assert start == datetime(2026, 11, 2, 15, 0)
    assert end == datetime(2026, 11, 3, 15, 0)


def test_kst_day_range_before_kst_midnight():
    start, end = kst_day_range_utc(datetime(2026, 11, 2, 14, 59))

    assert start == datetime(2026, 11, 1, 15, 0)
    assert end == datetime(2026, 11, 2, 15, 0)
