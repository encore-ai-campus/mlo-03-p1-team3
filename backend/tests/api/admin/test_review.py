from sqlalchemy import text

from app.api.loans.calc import due_dates
from app.core.time import kst_today
from tests.conftest import ledger_matches_balance, login, recorded_events

ADMIN = "/api/v1/admin/loans"


def submit(client, customer, product="car", amount=30_000_000, term=60):
    login(client, customer)
    response = client.post("/api/v1/loans/applications",
                           json={"product_code": product, "amount": amount, "term_months": term})
    return response.json()["application_id"]


def test_pending_list(client, make_user):
    app_id = submit(client, make_user(is_employed=False), product="home", amount=300_000_000, term=360)
    login(client, make_user(role="bank_employee"))

    response = client.get(f"{ADMIN}/pending?limit=50")

    assert response.status_code == 200
    assert response.json() == [{"application_id": app_id, "product_code": "home", "amount": 300_000_000,
                                "product_max_amount": 600_000_000, "term_months": 360, "is_employed": False}]


def test_approve_disburses_and_schedules(client, make_user, engine):
    customer = make_user()
    app_id = submit(client, customer)
    employee = make_user(role="bank_employee")
    login(client, employee)

    response = client.post(f"{ADMIN}/{app_id}/approve")

    assert response.status_code == 200
    assert response.json() == {"status": "repaying"}
    with engine.connect() as conn:
        balance = conn.execute(text("SELECT balance FROM accounts WHERE id = :a"),
                               {"a": customer["account_id"]}).scalar()
        entry = conn.execute(text("SELECT entry_type, amount FROM ledger_entries WHERE account_id = :a"),
                             {"a": customer["account_id"]}).one()
        loan = conn.execute(text("SELECT status, reviewed_by, reviewed_at IS NOT NULL, approved_at IS NOT NULL"
                                 " FROM loan_applications WHERE id = :i"), {"i": app_id}).one()
        rows = conn.execute(text("SELECT installment_number, due_date, amount, status"
                                 " FROM loan_repayments WHERE loan_application_id = :i ORDER BY installment_number"),
                            {"i": app_id}).all()
    assert balance == 30_000_000
    assert tuple(entry) == ("loan_disbursement", 30_000_000)
    assert tuple(loan) == ("repaying", employee["id"], 1, 1)
    assert len(rows) == 60
    assert rows[0].due_date == due_dates(kst_today(), 1)[0]
    assert sum(r.amount for r in rows) == 30_000_000
    assert {r.amount for r in rows} == {500_000}
    assert {r.status for r in rows} == {"scheduled"}
    assert ledger_matches_balance(engine, customer["account_id"])
    event = recorded_events("loan_review")[0]
    assert (event["outcome"], event["reason"]) == ("success", "approved")
    assert event["properties"] == {"product_code": "car", "term_months": 60, "amount_band": "over_1m"}


def test_reject_sets_status(client, make_user, engine):
    customer = make_user()
    app_id = submit(client, customer)
    employee = make_user(role="bank_employee")
    login(client, employee)

    response = client.post(f"{ADMIN}/{app_id}/reject")

    assert response.json() == {"status": "rejected"}
    with engine.connect() as conn:
        loan = conn.execute(text("SELECT status, reviewed_by, approved_at FROM loan_applications WHERE id = :i"),
                            {"i": app_id}).one()
        repayments = conn.execute(text("SELECT COUNT(*) FROM loan_repayments")).scalar()
        balance = conn.execute(text("SELECT balance FROM accounts WHERE id = :a"),
                               {"a": customer["account_id"]}).scalar()
    assert tuple(loan) == ("rejected", employee["id"], None)
    assert repayments == 0 and balance == 0
    assert recorded_events("loan_review")[0]["reason"] == "rejected"
    login(client, customer)
    assert client.post("/api/v1/loans/applications",
                       json={"product_code": "car", "amount": 10_000_000, "term_months": 12}).status_code == 200


def test_approve_not_pending_409(client, make_user):
    app_id = submit(client, make_user())
    login(client, make_user(role="bank_employee"))
    client.post(f"{ADMIN}/{app_id}/approve")

    for action in ("approve", "reject"):
        response = client.post(f"{ADMIN}/{app_id}/{action}")
        assert response.status_code == 409
        assert response.json()["code"] == "application_not_pending"


def test_unknown_application_404(client, make_user):
    login(client, make_user(role="bank_employee"))

    response = client.post(f"{ADMIN}/999999/approve")

    assert response.status_code == 404
    assert response.json()["code"] == "application_not_found"


def test_customer_calls_admin_403(client, make_user):
    app_id = submit(client, make_user())

    assert client.get(f"{ADMIN}/pending").status_code == 403
    assert client.post(f"{ADMIN}/{app_id}/approve").status_code == 403


def test_employee_cannot_apply_403(client, make_user):
    login(client, make_user(role="bank_employee"))

    response = client.post("/api/v1/loans/applications",
                           json={"product_code": "car", "amount": 10_000_000, "term_months": 12})

    assert response.status_code == 403
