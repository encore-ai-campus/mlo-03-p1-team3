from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection


def sent_between(conn: Connection, account_id: int, start: datetime, end: datetime) -> int:
    return int(conn.execute(
        text("SELECT COALESCE(-SUM(amount), 0) FROM ledger_entries WHERE account_id = :a"
             " AND entry_type = 'transfer_out' AND created_at >= :s AND created_at < :e"),
        {"a": account_id, "s": start, "e": end},
    ).scalar())
