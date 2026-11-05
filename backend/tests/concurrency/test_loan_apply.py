from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from tests.conftest import login


def test_parallel_apply(settings, engine, make_user):
    user = make_user()
    app = create_app(settings)

    def apply(_):
        with TestClient(app) as c:
            login(c, user)
            return c.post("/api/v1/loans/applications",
                          json={"product_code": "car", "amount": 10_000_000, "term_months": 12}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(apply, range(2)))

    assert statuses == [200, 409]
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM loan_applications")).scalar() == 1
