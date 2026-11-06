from datetime import date, datetime, timedelta, timezone

KST_OFFSET = timedelta(hours=9)
KST = timezone(KST_OFFSET, "Asia/Seoul")


def kst_now() -> datetime:
    """DB DATETIME에 저장할 시간대 없는 한국 시각."""
    return datetime.now(KST).replace(tzinfo=None)


def kst_iso(value: datetime | None = None) -> str:
    """한국 시각을 +09:00 오프셋과 함께 직렬화한다."""
    if value is None:
        return datetime.now(KST).isoformat()
    if value.tzinfo is None:
        value = value.replace(tzinfo=KST)
    return value.astimezone(KST).isoformat()


def kst_day_range(now_kst: datetime) -> tuple[datetime, datetime]:
    """한국 시간 오늘 0시부터 다음 날 0시까지의 DB 조회 범위."""
    if now_kst.tzinfo is not None:
        now_kst = now_kst.astimezone(KST).replace(tzinfo=None)
    start = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def kst_today() -> date:
    return kst_now().date()
