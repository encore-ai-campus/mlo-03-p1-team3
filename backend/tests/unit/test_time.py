from datetime import UTC, datetime, timedelta

from app.core.time import KST, kst_day_range, kst_iso, kst_now


def test_kst_day_range_after_midnight():
    start, end = kst_day_range(datetime(2026, 11, 3, 0, 30))
    assert start == datetime(2026, 11, 3)
    assert end == datetime(2026, 11, 4)


def test_kst_day_range_before_midnight():
    start, end = kst_day_range(datetime(2026, 11, 2, 23, 59))
    assert start == datetime(2026, 11, 2)
    assert end == datetime(2026, 11, 3)


def test_aware_utc_input_uses_korean_calendar_day():
    assert kst_day_range(datetime(2026, 11, 2, 15, 30, tzinfo=UTC))[0] == datetime(2026, 11, 3)


def test_kst_storage_clock_is_naive_local_time():
    assert abs((kst_now() - datetime.now(KST).replace(tzinfo=None)).total_seconds()) < 1


def test_log_timestamp_preserves_instant_and_offset():
    source = datetime(2026, 11, 6, 5, 18, tzinfo=UTC)
    result = datetime.fromisoformat(kst_iso(source))
    assert result.hour == 14
    assert result.utcoffset() == timedelta(hours=9)
    assert result == source
    assert kst_iso(datetime(2026, 11, 6, 14, 18)).endswith('+09:00')
