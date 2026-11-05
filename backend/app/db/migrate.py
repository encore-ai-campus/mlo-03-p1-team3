"""migrations/*.sql을 번호 순서대로 한 번씩 적용한다.

python -m app.db.migrate
python -m app.db.migrate --seed-employee 01000000000 <비밀번호>
"""

import argparse
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _statements(sql: str) -> list[str]:
    return [part.strip() for part in sql.split(";\n") if part.strip().rstrip(";")]


def apply_migrations(engine: Engine) -> list[str]:
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version VARCHAR(100) NOT NULL PRIMARY KEY,"
            " applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6))"
        ))
        done = set(conn.execute(text("SELECT version FROM schema_migrations")).scalars())

    applied = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.stem in done:
            continue
        with engine.begin() as conn:
            for statement in _statements(path.read_text(encoding="utf-8")):
                conn.execute(text(statement.rstrip(";")))
            conn.execute(text("INSERT INTO schema_migrations (version) VALUES (:v)"), {"v": path.stem})
        applied.append(path.stem)
    return applied


def seed_employee(engine: Engine, phone: str, password: str) -> int:
    from app.core.security import hash_password

    with engine.begin() as conn:
        existing = conn.execute(text("SELECT id FROM users WHERE phone_number = :p"), {"p": phone}).scalar()
        if existing:
            return existing
        return conn.execute(
            text(
                "INSERT INTO users (phone_number, password_hash, name, birth_year, gender, marital_status,"
                " is_employed, role) VALUES (:p, :h, '포도은행 직원', 1990, 'female', 'single', TRUE, 'bank_employee')"
            ),
            {"p": phone, "h": hash_password(password)},
        ).lastrowid


def main() -> None:
    from app.core.config import Settings
    from app.db.mariadb import make_engine

    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-employee", nargs=2, metavar=("PHONE", "PASSWORD"))
    args = parser.parse_args()
    engine = make_engine(Settings.from_env().mariadb_url)
    print("applied:", apply_migrations(engine))
    if args.seed_employee:
        print("employee id:", seed_employee(engine, *args.seed_employee))


if __name__ == "__main__":
    main()
