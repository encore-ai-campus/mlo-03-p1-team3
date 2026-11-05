from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from tests.conftest import ledger_matches_balance, login


def test_parallel_approve(settings, engine, make_user):
    customer = make_user()
    employee = make_user(role="bank_employee")
    app = create_app(settings)
    with TestClient(app) as c:
        login(c, customer)
        app_id = c.post("/api/v1/loans/applications",
                        json={"product_code": "car", "amount": 10_000_000, "term_months": 12}).json()["application_id"]

    def approve(_):
        with TestClient(app) as c:
            login(c, employee)
            return c.post(f"/api/v1/admin/loans/{app_id}/approve").status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(approve, range(2)))

    assert statuses == [200, 409]
    with engine.connect() as conn:
        disbursements = conn.execute(text("SELECT COUNT(*) FROM ledger_entries"
                                          " WHERE entry_type = 'loan_disbursement'")).scalar()
        repayments = conn.execute(text("SELECT COUNT(*) FROM loan_repayments")).scalar()
    assert disbursements == 1
    assert repayments == 12
    assert ledger_matches_balance(engine, customer["account_id"])
