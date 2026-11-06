"""migrations/*.sql을 번호 순서대로 한 번씩 적용한다.

python -m app.db.migrate
직원 계정 준비: python -m app.db.employee (.env 환경변수 사용)
"""

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


def main() -> None:
    from app.core.config import Settings
    from app.db.mariadb import make_engine

    engine = make_engine(Settings.from_env().mariadb_url)
    print("applied:", apply_migrations(engine))


if __name__ == "__main__":
    main()
