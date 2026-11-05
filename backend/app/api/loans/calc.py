"""상환 계산. 이자 없이 원금만 나눠 갚는다. 금액은 원 단위 정수."""

import calendar
from datetime import date


def monthly_installment(principal: int, months: int) -> int:
    """매달 내는 돈 = 원금 ÷ 개월 수, 원 단위 내림."""
    return principal // months


def schedule(principal: int, months: int) -> list[int]:
    """회차별 금액. 마지막 회차가 내림으로 남은 원을 함께 갚아서 합계가 원금과 같다."""
    payment = monthly_installment(principal, months)
    return [payment] * (months - 1) + [principal - payment * (months - 1)]


def due_dates(approved_on: date, months: int) -> list[date]:
    """승인일과 같은 날. 그 달에 그날이 없으면 말일."""
    result = []
    for k in range(1, months + 1):
        index = approved_on.month - 1 + k
        year, month = approved_on.year + index // 12, index % 12 + 1
        result.append(date(year, month, min(approved_on.day, calendar.monthrange(year, month)[1])))
    return result
