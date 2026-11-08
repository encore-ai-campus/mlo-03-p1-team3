"""Offline history planner and explicit, non-retrying lab database writer."""

import argparse
import calendar
import hashlib
import json
import math
import os
import random
import sys
import time
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path
from uuid import UUID

BACKEND = Path("/opt/podobank/backend")
sys.path.insert(
    0,
    str(
        BACKEND if BACKEND.exists() else Path(__file__).resolve().parents[1] / "backend"
    ),
)

from app.core.config import TRANSFER_DAILY_LIMIT, TRANSFER_MAX_AMOUNT
from app.core.time import kst_iso, kst_now


def shift_month(value, months):
    index = value.year * 12 + value.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return value.replace(
        year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1])
    )


def period(months, now=None):
    if months < 1:
        raise ValueError("months")
    end = (now or kst_now()).replace(hour=0, minute=0, second=0, microsecond=0)
    return shift_month(end, -months), end


def poisson(rng, mean):
    threshold, product, count = math.exp(-mean), 1.0, 0
    while product > threshold:
        product *= rng.random()
        count += 1
    return count - 1


def validate_safety(accounts, ledger, session_count, event_count):
    """Reject everything except an untouched account_pool snapshot."""
    if not accounts or session_count or event_count:
        raise ValueError("unsafe pool")
    grouped = defaultdict(list)
    for row in ledger:
        grouped[row["account_id"]].append(row)
    for account in accounts:
        rows = grouped[account["id"]]
        if (
            len(rows) != 1
            or rows[0]["entry_type"] != "deposit"
            or rows[0]["amount"] != account["balance"]
            or rows[0]["balance_after"] != account["balance"]
            or account["balance"] not in (30_000, 30_000_000)
        ):
            raise ValueError("unsafe ledger")


def plan_months(accounts, months=12, seed=20261108, now=None, event_tools=None):
    """Yield one calendar-month batch; only balances/devices survive a yield.

    Partial boundary months receive prorated Poisson activity. Salary is included
    only if the 25th belongs to the requested interval.
    """
    if event_tools is None:
        from app.api.events import service as event_tools
    start, end = period(months, now)
    rng = random.Random(seed)
    accounts = sorted(accounts, key=lambda a: a["id"])
    if not accounts:
        raise ValueError("empty pool")
    balances = {a["id"]: 0 for a in accounts}

    def uid():
        return str(UUID(int=rng.getrandbits(128), version=4))

    devices = {
        u: [
            (uid(), rng.choice(("web", "ios-app", "android-app")))
            for _ in range(rng.randint(1, 2))
        ]
        for u in sorted({a["user_id"] for a in accounts})
    }
    cursor = start
    while cursor < end:
        boundary = min(shift_month(cursor.replace(day=1), 1), end)
        cutoff = min(boundary, end - timedelta(minutes=1))
        operations, sessions, ledger, events = [], [], [], []
        skipped = 0
        fraction = (boundary - cursor).total_seconds() / (
            calendar.monthrange(cursor.year, cursor.month)[1] * 86400
        )

        def moment(cursor=cursor, cutoff=cutoff):
            # Rejection sampling gives daytime four times the overnight weight.
            while True:
                value = cursor + timedelta(
                    seconds=rng.randrange(int((cutoff - cursor).total_seconds()))
                )
                if 7 <= value.hour <= 23 or rng.random() < 0.25:
                    return value

        for index, a in enumerate(accounts):
            aid = a["id"]
            small = a["balance"] == 30_000
            if cursor == start:
                operations.append(
                    (
                        start + timedelta(microseconds=1),
                        aid,
                        "deposit",
                        100_000 if small else rng.randint(1000, 5000) * 1000,
                        None,
                    )
                )
            salary = cursor.replace(day=25, hour=9) + timedelta(
                seconds=rng.randrange(7200)
            )
            if cursor <= salary < cutoff:
                operations.append(
                    (
                        salary,
                        aid,
                        "deposit",
                        rng.randint(100, 300) * 1000
                        if small
                        else rng.randint(2000, 4000) * 1000,
                        None,
                    )
                )
            for _ in range(poisson(rng, 15 * fraction) if len(accounts) > 1 else 0):
                recipient = rng.randrange(len(accounts) - 1)
                if recipient >= index:
                    recipient += 1
                amount = (
                    min(300, max(10, round(rng.lognormvariate(math.log(40), 0.85))))
                    * 1000
                )
                operations.append(
                    (moment(), aid, "transfer", amount, accounts[recipient]["id"])
                )
        for user, user_devices in devices.items():
            for _ in range(poisson(rng, 20 * fraction)):
                created = moment()
                last = created + timedelta(minutes=rng.randint(1, 15))
                reason = "logout" if rng.random() < 0.6 else "idle_timeout"
                ended = last + timedelta(minutes=10 if reason == "idle_timeout" else 0)
                if ended >= end:
                    created -= timedelta(minutes=26)
                    last -= timedelta(minutes=26)
                    ended -= timedelta(minutes=26)
                device, client = rng.choice(user_devices)
                sessions.append(
                    {
                        "token_hash": hashlib.sha256(
                            rng.getrandbits(256).to_bytes(32, "big")
                        ).hexdigest(),
                        "user_id": user,
                        "device_id": device,
                        "client": client,
                        "user_agent": None,
                        "login_method": "password",
                        "created_at": created,
                        "last_seen_at": last,
                        "ended_at": ended,
                        "end_reason": reason,
                    }
                )

        def event(kind, at, amount=0, events=events):
            value = event_tools.build_event(
                kind,
                "success",
                "completed",
                source="history_seed",
                request_id=None,
                duration_ms=None,
                properties={"method": "password"}
                if kind == "login"
                else {"amount_band": event_tools.amount_band(abs(amount))},
            )
            value.update(
                event_id=uid(), occurred_at=kst_iso(at), instance="history_seed"
            )
            event_tools._check_keys(value)
            events.append(value)

        def entry(aid, kind, amount, at, transaction, ledger=ledger):
            balances[aid] += amount
            ledger.append(
                {
                    "transaction_id": transaction,
                    "account_id": aid,
                    "entry_type": kind,
                    "amount": amount,
                    "balance_after": balances[aid],
                    "created_at": at,
                }
            )

        daily = Counter()
        for at, aid, kind, amount, recipient in sorted(operations):
            if kind == "transfer":
                key = (aid, at.date())
                if (
                    balances[aid] < amount
                    or amount > TRANSFER_MAX_AMOUNT
                    or daily[key] + amount > TRANSFER_DAILY_LIMIT
                ):
                    skipped += 1
                    continue
                transaction = uid()
                daily[key] += amount
                entry(aid, "transfer_out", -amount, at, transaction)
                entry(recipient, "transfer_in", amount, at, transaction)
            else:
                entry(aid, kind, amount, at, uid())
            event(kind, at, amount)
        if boundary == end:
            corrections = sorted(
                (
                    end - timedelta(seconds=rng.randint(1, 60)),
                    a["id"],
                    a["balance"] - balances[a["id"]],
                )
                for a in accounts
            )
            for at, aid, difference in corrections:
                if difference:
                    kind = "deposit" if difference > 0 else "withdrawal"
                    entry(aid, kind, difference, at, uid())
                    event(kind, at, difference)
        for session in sessions:
            event("login", session["created_at"])
        sessions.sort(key=lambda s: s["created_at"])
        events.sort(key=lambda e: e["occurred_at"])
        yield {
            "ledger": ledger,
            "sessions": sessions,
            "events": events,
            "skipped": skipped,
        }
        cursor = boundary


POOL = " JOIN accounts a ON a.id=l.account_id JOIN users u ON u.id=a.user_id WHERE u.name LIKE 'LOAD-POOL-%'"


def snapshot(conn, collection, lock=False):
    from sqlalchemy import text

    accounts = [
        dict(r)
        for r in conn.execute(
            text(
                "SELECT a.id,a.user_id,a.balance FROM accounts a JOIN users u ON u.id=a.user_id "
                "WHERE u.name LIKE 'LOAD-POOL-%' ORDER BY a.id"
                + (" FOR UPDATE" if lock else "")
            )
        ).mappings()
    ]
    ledger = [
        dict(r)
        for r in conn.execute(
            text(
                "SELECT l.* FROM ledger_entries l"
                + POOL
                + (" FOR UPDATE" if lock else "")
            )
        ).mappings()
    ]
    sessions = conn.execute(
        text(
            "SELECT COUNT(*) FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE u.name LIKE 'LOAD-POOL-%'"
        )
    ).scalar_one()
    validate_safety(
        accounts,
        ledger,
        sessions,
        collection.count_documents({"source": "history_seed"}),
    )
    return accounts


def verify(conn, collection, end):
    from sqlalchemy import text

    checks = {}
    queries = {
        "balances": "SELECT COUNT(*) FROM (SELECT a.id FROM accounts a JOIN users u ON u.id=a.user_id "
        "LEFT JOIN ledger_entries l ON l.account_id=a.id WHERE u.name LIKE 'LOAD-POOL-%' "
        "GROUP BY a.id,a.balance HAVING COALESCE(SUM(l.amount),0)<>a.balance OR "
        "COALESCE((SELECT x.balance_after FROM ledger_entries x WHERE x.account_id=a.id "
        "ORDER BY x.id DESC LIMIT 1),-1)<>a.balance) bad",
        "transfer_pairs": "SELECT COUNT(*) FROM (SELECT l.transaction_id FROM ledger_entries l"
        + POOL
        + " AND l.entry_type IN ('transfer_out','transfer_in') GROUP BY l.transaction_id "
        "HAVING COUNT(*)<>2 OR SUM(l.amount)<>0 OR SUM(l.entry_type='transfer_out')<>1 "
        "OR SUM(l.entry_type='transfer_in')<>1 OR COUNT(DISTINCT l.account_id)<>2) bad",
        "today": "SELECT COUNT(*) FROM ledger_entries l"
        + POOL
        + " AND l.created_at>=:end AND l.created_at<:tomorrow",
        "negative": "SELECT COUNT(*) FROM ledger_entries l"
        + POOL
        + " AND l.balance_after<0",
        "single_limit": "SELECT COUNT(*) FROM ledger_entries l"
        + POOL
        + " AND l.entry_type='transfer_out' AND (-l.amount>:single OR l.amount>=0)",
        "daily_limit": "SELECT COUNT(*) FROM (SELECT l.account_id,DATE(l.created_at) FROM ledger_entries l"
        + POOL
        + " AND l.entry_type='transfer_out' GROUP BY l.account_id,DATE(l.created_at) "
        "HAVING -SUM(l.amount)>:daily) bad",
    }
    params = {
        "end": end,
        "tomorrow": end + timedelta(days=1),
        "single": TRANSFER_MAX_AMOUNT,
        "daily": TRANSFER_DAILY_LIMIT,
    }
    for name, sql in queries.items():
        checks[name] = conn.execute(text(sql), params).scalar_one() == 0
    for kind, sql in {
        "transfer": "SELECT COUNT(*) FROM ledger_entries l"
        + POOL
        + " AND l.entry_type='transfer_out'",
        "login": "SELECT COUNT(*) FROM sessions s JOIN users u ON u.id=s.user_id WHERE u.name LIKE 'LOAD-POOL-%'",
    }.items():
        checks[kind + "_events"] = conn.execute(
            text(sql)
        ).scalar_one() == collection.count_documents(
            {"source": "history_seed", "event_type": kind}
        )
    return checks


def write_rows(engine, table, rows, progress, pause):
    from sqlalchemy import text

    if not rows:
        return
    columns = list(rows[0])
    sql = text(
        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join(':' + c for c in columns)})"
    )
    for offset in range(0, len(rows), 5000):
        chunk = rows[offset : offset + 5000]
        progress["phase"] = table
        progress["in_flight"] = len(chunk)
        with engine.begin() as conn:
            conn.execute(sql, chunk)
        progress[table] += len(chunk)
        progress["in_flight"] = 0
        time.sleep(pause)


def main(argv=None):
    started = time.monotonic()
    progress = {
        "ledger_entries": 0,
        "sessions": 0,
        "events": 0,
        "skipped": 0,
        "deleted_initial": 0,
        "completed_batches": 0,
        "in_flight": 0,
        "phase": "arguments",
    }
    engine = client = None
    try:

        class JsonParser(argparse.ArgumentParser):
            def error(self, message):
                raise ValueError("arguments")

        parser = JsonParser(description=__doc__)
        parser.add_argument("--months", type=int, default=12)
        parser.add_argument("--seed", type=int, default=20261108)
        parser.add_argument("--chunk-pause", type=float, default=0.02)
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--verify", action="store_true")
        args = parser.parse_args(argv)
        if (
            args.months < 1
            or not math.isfinite(args.chunk_pause)
            or args.chunk_pause < 0
        ):
            raise ValueError("arguments")
        from app.db.mariadb import make_engine
        from pymongo import MongoClient
        from sqlalchemy import text

        engine = make_engine(os.environ["MARIADB_URL"])
        client = MongoClient(
            os.environ["MONGODB_URL"],
            retryWrites=False,
            retryReads=False,
            serverSelectionTimeoutMS=5000,
        )
        collection = client[os.environ["MONGODB_DB"]]["events_bronze"]
        now = kst_now()
        _, end = period(args.months, now)
        if args.verify:
            progress["phase"] = "verify"
            with engine.connect() as conn:
                progress["checks"] = verify(conn, collection, end)
            progress["ok"] = all(progress["checks"].values())
        else:
            progress["phase"] = "safety"
            with engine.connect() as conn:
                accounts = snapshot(conn, collection)
            if not args.dry_run:
                with engine.begin() as conn:
                    locked = snapshot(conn, collection, lock=True)
                    if locked != accounts:
                        raise ValueError("changed snapshot")
                    progress.update(phase="delete_initial", in_flight=len(accounts))
                    result = conn.execute(text("DELETE l FROM ledger_entries l" + POOL))
                    deleted = result.rowcount
                progress["deleted_initial"] = deleted
                progress["in_flight"] = 0
            estimated = 0
            for batch in plan_months(accounts, args.months, args.seed, now):
                progress["skipped"] += batch["skipped"]
                if args.dry_run:
                    for key, dest in [
                        ("ledger", "ledger_entries"),
                        ("sessions", "sessions"),
                        ("events", "events"),
                    ]:
                        progress[dest] += len(batch[key])
                        estimated += sum(
                            len(json.dumps(row, default=str).encode())
                            for row in batch[key]
                        )
                else:
                    write_rows(
                        engine,
                        "ledger_entries",
                        batch["ledger"],
                        progress,
                        args.chunk_pause,
                    )
                    write_rows(
                        engine,
                        "sessions",
                        batch["sessions"],
                        progress,
                        args.chunk_pause,
                    )
                    for offset in range(0, len(batch["events"]), 10000):
                        chunk = batch["events"][offset : offset + 10000]
                        progress.update(phase="events", in_flight=len(chunk))
                        try:
                            collection.insert_many(chunk, ordered=False)
                        except Exception as exc:
                            details = getattr(exc, "details", None)
                            if isinstance(details, dict) and "nInserted" in details:
                                progress["events"] += details["nInserted"]
                                progress["in_flight"] -= details["nInserted"]
                            raise
                        progress["events"] += len(chunk)
                        progress["in_flight"] = 0
                progress["completed_batches"] += 1
                del batch  # Release the previous month before requesting the next batch.
            if args.dry_run:
                progress["estimated_json_bytes"] = estimated
                progress["size_note"] = (
                    "logical JSON size; database indexes/storage overhead excluded"
                )
                progress["ok"] = True
            else:
                progress["phase"] = "final_verify"
                with engine.connect() as conn:
                    progress["checks"] = verify(conn, collection, end)
                progress["ok"] = all(progress["checks"].values())
    except Exception as exc:  # noqa: BLE001 - Never disclose SQL parameters or connection strings.
        progress.update(ok=False, error=type(exc).__name__)
        if progress["in_flight"]:
            progress["commit_status_unknown"] = True
    finally:
        if client is not None:
            client.close()
        if engine is not None:
            engine.dispose()
    progress["elapsed_seconds"] = round(time.monotonic() - started, 3)
    print(json.dumps(progress))
    return 0 if progress["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
