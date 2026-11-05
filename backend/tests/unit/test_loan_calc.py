"""이자 없이 원금만 나눠 갚는다."""
from datetime import date

import pytest

from app.api.loans.calc import due_dates, monthly_installment, schedule


def test_even_split():
    assert monthly_installment(12_000_000, 12) == 1_000_000
    assert schedule(12_000_000, 12) == [1_000_000] * 12


def test_remainder_goes_to_last_installment():
    rows = schedule(10_000_000, 12)
    assert rows[:-1] == [833_333] * 11
    assert rows[-1] == 833_337


@pytest.mark.parametrize(("principal", "terms"), [
    (50_000_000, [12, 24, 36, 48, 60, 120]),
    (200_000_000, [12, 24]),
    (600_000_000, [120, 240, 360]),
    (1_000_000, [12, 360]),
])
def test_schedule_sums_to_principal(principal, terms):
    for months in terms:
        rows = schedule(principal, months)
        assert len(rows) == months
        assert sum(rows) == principal
        assert all(isinstance(r, int) and r > 0 for r in rows)
        assert all(r == monthly_installment(principal, months) for r in rows[:-1])


def test_due_dates_month_end():
    assert due_dates(date(2027, 1, 31), 3) == [date(2027, 2, 28), date(2027, 3, 31), date(2027, 4, 30)]
    assert due_dates(date(2028, 1, 31), 1) == [date(2028, 2, 29)]


def test_due_dates_year_rollover():
    assert due_dates(date(2026, 11, 4), 3) == [date(2026, 12, 4), date(2027, 1, 4), date(2027, 2, 4)]
