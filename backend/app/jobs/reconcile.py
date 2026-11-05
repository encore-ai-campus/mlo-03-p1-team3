"""일 마감 대사. 계좌마다 원장 amount 합계 = 잔액인지 확인한다.

python -m app.jobs.reconcile
"""
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.api.events.service import EventSink, make_sink, record, transaction
from app.core.config import Settings
from app.db.mariadb import make_engine


@dataclass(frozen=True)
class ReconcileResult:
    checked: int
    mismatched_account_ids: list[int]


def reconcile(engine: Engine, sink: EventSink) -> ReconcileResult:
    """한 SELECT로 읽어 같은 시점의 잔액·원장을 비교한다. 이벤트에는 개수만 남기고 계좌 ID는 결과로만 돌려준다."""
    with transaction(engine, sink) as conn:
        rows = conn.execute(text(
            "SELECT a.id, a.balance, COALESCE(SUM(l.amount), 0) AS ledger_sum FROM accounts a"
            " LEFT JOIN ledger_entries l ON l.account_id = a.id GROUP BY a.id, a.balance ORDER BY a.id"
        )).mappings().all()
        mismatched = [r["id"] for r in rows if r["balance"] != r["ledger_sum"]]
        record(conn, None, "reconciliation", "failure" if mismatched else "success",
               "ledger_mismatch" if mismatched else "completed",
               {"checked_accounts": len(rows), "mismatched_accounts": len(mismatched)}, source="batch")
    return ReconcileResult(checked=len(rows), mismatched_account_ids=mismatched)


def main() -> None:
    settings = Settings.from_env()
    result = reconcile(make_engine(settings.mariadb_url), make_sink(settings))
    print(f"checked={result.checked} mismatched={len(result.mismatched_account_ids)}")
    if result.mismatched_account_ids:
        print("mismatched_account_ids=" + ",".join(map(str, result.mismatched_account_ids)))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
