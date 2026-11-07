"""Prepare a reusable lab-only customer pool without deleting existing data.

Run with the API environment loaded and --seed on the API VM. Credentials are
written only to the requested .env file, never stdout, reports or exceptions.
"""
import argparse
import json
import os
import secrets
import sys
from pathlib import Path
from uuid import uuid4


def seed_pool(engine, count, prefix, password):
    from app.core.security import hash_password
    from sqlalchemy import text

    phones = [f'{prefix}{i:05d}' for i in range(count)]
    password_hash = hash_password(password)
    with engine.begin() as conn:
        existing = conn.execute(text('SELECT COUNT(*) FROM users WHERE phone_number LIKE :p'),
                                {'p': prefix + '%'}).scalar_one()
        if existing:
            raise ValueError('Pool prefix already exists; refusing to overwrite accounts')
        conn.execute(text('INSERT INTO users (phone_number,password_hash,name,birth_year,gender,'
                          'marital_status,is_employed,role) VALUES (:phone,:hash,:name,1995,'
                          "'male','single',TRUE,'customer')"),
                     [{'phone': phone, 'hash': password_hash, 'name': f'LOAD-POOL-{i}'}
                      for i, phone in enumerate(phones)])
        rows = conn.execute(text('SELECT id,phone_number FROM users WHERE phone_number LIKE :p'),
                            {'p': prefix + '%'}).all()
        users = {phone: uid for uid, phone in rows}
        conn.execute(text('INSERT INTO accounts (user_id,account_number,balance) VALUES (:u,:n,:b)'),
                     [{'u': users[phone], 'n': '900' + phone, 'b': 30_000 if i % 10 == 9 else 30_000_000}
                      for i, phone in enumerate(phones)])
        rows = conn.execute(text('SELECT a.id,u.phone_number,a.balance FROM accounts a JOIN users u '
                                 'ON u.id=a.user_id WHERE u.phone_number LIKE :p'), {'p': prefix + '%'}).all()
        conn.execute(text('INSERT INTO ledger_entries (transaction_id,account_id,entry_type,amount,balance_after) '
                          "VALUES (:t,:a,'deposit',:b,:b)"),
                     [{'t': str(uuid4()), 'a': aid, 'b': balance} for aid, _phone, balance in rows])
    return [{'phone_number': phone, 'password': password} for phone in phones]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', action='store_true', required=True)
    parser.add_argument('--count', type=int, default=10000)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.name != '.env' or not 2 <= args.count <= 10000:
        parser.error('Output must be a private .env file; count must be 2..10000')
    if args.output.exists():
        print('Pool .env already exists; no database writes performed')
        return 0
    sys.path.insert(0, str(Path('/opt/podobank/backend')))
    from app.db.mariadb import make_engine
    engine = make_engine(os.environ['MARIADB_URL'])
    # Reserve the private file first, so concurrent invocations cannot both seed.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        records = seed_pool(engine, args.count, f'019{secrets.randbelow(1000):03d}', secrets.token_urlsafe(24))
        with os.fdopen(fd, 'w') as stream:
            stream.write('PODOBANK_ACCOUNTS_JSON=' + json.dumps(records, separators=(',', ':')) + '\n')
        print(json.dumps({'prepared_accounts': len(records), 'database_reset': False,
                          'financial_api_preparation_calls': 0}))
    except Exception as error:  # noqa: BLE001 - SQL exceptions may contain credentials/parameters
        try:
            os.close(fd)
        except OSError:
            pass
        args.output.unlink(missing_ok=True)
        print('Pool preparation failed: ' + type(error).__name__, file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
