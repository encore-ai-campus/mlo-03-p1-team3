"""상환 배치. 기준일까지 기한이 된 회차를 출금하고, 연체 회차는 다시 시도한다.

python -m app.jobs.repayments --as-of-date 2027-01-03   (기본: 오늘, 한국 날짜)
"""
import argparse
from dataclasses import dataclass
from datetime import date

from sqlalchemy.engine import Engine

from app.api.events.service import EventSink, make_sink
from app.api.loans import repository, service
from app.core.config import Settings
from app.core.errors import AppError
from app.core.time import kst_today
from app.db.mariadb import make_engine, translate_db_errors, with_deadlock_retry


@dataclass(frozen=True)
class RepaymentResult:
    paid: int
    overdue: int
    recovered: int
    skipped: int


def run_repayments(engine: Engine, sink: EventSink, as_of: date) -> RepaymentResult:
    """대출 하나마다 짧은 트랜잭션으로 처리한다. 잠금 대기가 길면 그 대출은 건너뛰고 다음 실행에 맡긴다."""
    with engine.connect() as conn:
        application_ids = repository.due_application_ids(conn, as_of)
    total = {"paid": 0, "overdue": 0, "recovered": 0, "skipped": 0}
    for application_id in application_ids:
        try:
            with translate_db_errors():
                counts = with_deadlock_retry(lambda a=application_id: service.repay_due(engine, sink, a, as_of))
        except AppError:
            total["skipped"] += 1
            continue
        for k, v in counts.items():
            total[k] += v
    return RepaymentResult(**total)


def main() -> None:
    parser = argparse.ArgumentParser(description="상환 배치")
    parser.add_argument("--as-of-date", type=date.fromisoformat, default=None)
    args = parser.parse_args()
    settings = Settings.from_env()
    result = run_repayments(make_engine(settings.mariadb_url), make_sink(settings), args.as_of_date or kst_today())
    print(f"paid={result.paid} overdue={result.overdue} recovered={result.recovered} skipped={result.skipped}")


if __name__ == "__main__":
    main()
