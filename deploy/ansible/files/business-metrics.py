"""Bounded, read-only business snapshots for node_exporter's textfile collector.

No customer identifiers, balances, credentials or exception text are exported.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

LEDGER = ('deposit', 'withdrawal', 'transfer_out', 'transfer_in', 'loan_disbursement', 'loan_repayment', 'card_payment')
LOANS = ('pending', 'repaying', 'rejected', 'repaid')
REPAYMENTS = ('scheduled', 'paid', 'overdue')
EVENTS = ('deposit', 'withdrawal', 'transfer', 'loan_application', 'loan_review', 'loan_repayment', 'card_payment')


def sample(name, value, **labels):
    value = float(value)
    if not 0 <= value < float('inf'):
        raise ValueError('Invalid aggregate')
    suffix = '{' + ','.join(k + '=' + json.dumps(str(v)) for k, v in labels.items()) + '}' if labels else ''
    return name + suffix + ' ' + str(value)


def maria_snapshot():
    queries = [
        "SELECT 'ledger_entries',entry_type,COUNT(*) FROM ledger_entries GROUP BY entry_type",
        "SELECT 'loan_applications',status,COUNT(*) FROM loan_applications GROUP BY status",
        "SELECT 'loan_repayments',status,COUNT(*) FROM loan_repayments GROUP BY status",
        "SELECT 'card_payments','all',COUNT(*) FROM card_payments",
    ]
    sql = 'SET SESSION max_statement_time=5; START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY; ' + '; '.join(queries) + '; COMMIT;'
    result = subprocess.run(['mariadb', '--user=podobank-metrics', '--protocol=socket', '--batch', '--skip-column-names', 'podobank'],
                            input=sql, capture_output=True, text=True, timeout=25, check=True)
    actual = {}
    for line in result.stdout.splitlines():
        dataset, kind, count = line.split('\t')
        actual[dataset, kind] = int(count)
    expected = [('ledger_entries', k) for k in LEDGER] + [('loan_applications', k) for k in LOANS] + [('loan_repayments', k) for k in REPAYMENTS] + [('card_payments', 'all')]
    if set(actual) - set(expected) or ('card_payments', 'all') not in actual:
        raise ValueError('Unexpected aggregate shape')
    return [sample('podobank_db_records', actual.get((dataset, kind), 0), store='mariadb', dataset=dataset, kind=kind) for dataset, kind in expected]


def mongo_snapshot(script):
    result = subprocess.run(['mongosh', '--nodb', '--quiet', '--file', str(script)], capture_output=True,
                            text=True, timeout=25, check=True)
    data = json.loads(result.stdout)
    if set(data['collections']) != {'events_bronze', 'card_payment_locations'}:
        raise ValueError('Unexpected collection set')
    lines = [sample('podobank_db_records', count, store='mongodb', dataset=name, kind='all') for name, count in data['collections'].items()]
    actual = {(row['event_type'], row['outcome']): row['count'] for row in data['events']}
    expected = {(e, o) for e in EVENTS for o in ('success', 'failure')}
    if set(actual) - expected:
        raise ValueError('Unexpected event aggregate')
    lines.extend(sample('podobank_mongo_events', actual.get((e, o), 0), event_type=e, outcome=o)
                 for e, o in sorted(expected))
    return lines


def collect(store, output, mongo_script):
    started = time.monotonic()
    now = time.time()
    # Failed collection replaces old counts instead of leaving a stale healthy snapshot.
    try:
        lines = maria_snapshot() if store == 'mariadb' else mongo_snapshot(mongo_script)
        success = True
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        lines, success = [], False
    lines.extend([sample('podobank_business_collect_success', int(success), store=store),
                  sample('podobank_business_collect_attempt_timestamp_seconds', now, store=store),
                  sample('podobank_business_collect_duration_seconds', time.monotonic() - started, store=store)])
    if success:
        lines.append(sample('podobank_business_collect_success_timestamp_seconds', time.time(), store=store))
    temporary = output.with_suffix('.prom.tmp')
    temporary.write_text('\n'.join(lines) + '\n')
    temporary.chmod(0o644)
    os.replace(temporary, output)
    return success


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', choices=('mariadb', 'mongodb'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mongo-script', type=Path, default=Path(__file__).with_name('business-metrics.js'))
    args = parser.parse_args()
    raise SystemExit(0 if collect(args.store, args.output, args.mongo_script) else 1)
