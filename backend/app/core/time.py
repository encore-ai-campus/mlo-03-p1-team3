from datetime import UTC, date, datetime, timedelta

KST_OFFSET = timedelta(hours=9)


def utc_now() -> datetime:
    """DB DATETIME과 맞추려고 tz 정보 없는 UTC 시각을 돌려준다."""
    return datetime.now(UTC).replace(tzinfo=None)


def kst_day_range_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    """한국 시간 '오늘' 0시~24시를 UTC 범위로 바꾼다."""
    kst_midnight = (now_utc + KST_OFFSET).replace(hour=0, minute=0, second=0, microsecond=0)
    start = kst_midnight - KST_OFFSET
    return start, start + timedelta(days=1)


def kst_today() -> date:
    return (utc_now() + KST_OFFSET).date()
