from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app


def test_parallel_wrong_passwords_counted(settings, engine, make_user):
    user = make_user()
    app = create_app(settings)

    def attempt(_):
        with TestClient(app) as c:
            return c.post("/api/v1/auth/login",
                          json={"phone_number": user["phone"], "password": "wrong-password"}).status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        statuses = list(pool.map(attempt, range(10)))

    with engine.connect() as conn:
        count = conn.execute(text("SELECT failed_login_count FROM users WHERE id = :id"), {"id": user["id"]}).scalar()
    assert set(statuses) <= {401, 423}
    assert count == statuses.count(401)
    assert count >= 5
    with TestClient(app) as c:
        locked = c.post("/api/v1/auth/login", json={"phone_number": user["phone"], "password": user["password"]})
    assert locked.status_code == 423
