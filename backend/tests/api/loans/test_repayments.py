import uuid

from sqlalchemy import text

from app.jobs.repayments import run_repayments
from tests.conftest import ledger_matches_balance, login, recorded_events


def approved_loan(client, make_user, amount=10_000_000, term=12):
    """신청 → 직원 승인까지 마친 대출을 만들고 고객으로 다시 로그인한다."""
    customer = make_user()
    login(client, customer)
    app_id = client.post("/api/v1/loans/applications",
                         json={"product_code": "car", "amount": amount, "term_months": term}).json()["application_id"]
    login(client, make_user(role="bank_employee"))
    client.post(f"/api/v1/admin/loans/{app_id}/approve")
    login(client, customer)
    return customer, app_id


def set_balance(engine, account_id, value):
    with engine.begin() as conn:
        current = conn.execute(text("SELECT balance FROM accounts WHERE id = :a"), {"a": account_id}).scalar()
        if current == value:
            return
        conn.execute(text("UPDATE accounts SET balance = :b WHERE id = :a"), {"b": value, "a": account_id})
        conn.execute(text("INSERT INTO ledger_entries (transaction_id, account_id, entry_type, amount, balance_after)"
                          " VALUES (:t, :a, :e, :m, :b)"),
                     {"t": str(uuid.uuid4()), "a": account_id, "e": "deposit" if value > current else "withdrawal",
                      "m": value - current, "b": value})


def installments(engine, app_id):
    with engine.connect() as conn:
        return conn.execute(text("SELECT installment_number AS n, due_date, amount, status FROM loan_repayments"
                                 " WHERE loan_application_id = :i ORDER BY installment_number"),
                            {"i": app_id}).mappings().all()


def balance(engine, account_id):
    with engine.connect() as conn:
        return conn.execute(text("SELECT balance FROM accounts WHERE id = :a"), {"a": account_id}).scalar()


def repayment_ledger_count(engine, account_id):
    with engine.connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM ledger_entries WHERE account_id = :a"
                                 " AND entry_type = 'loan_repayment'"), {"a": account_id}).scalar()


def results(engine):
    return [e["properties"]["result"] for e in recorded_events("loan_repayment")]


def test_due_paid(client, make_user, engine, sink):
    customer, app_id = approved_loan(client, make_user)
    first = installments(engine, app_id)[0]
    set_balance(engine, customer["account_id"], first.amount + 100)

    result = run_repayments(engine, sink, first.due_date)

    assert (result.paid, result.overdue) == (1, 0)
    assert installments(engine, app_id)[0].status == "paid"
    assert installments(engine, app_id)[1].status == "scheduled"
    assert balance(engine, customer["account_id"]) == 100
    assert repayment_ledger_count(engine, customer["account_id"]) == 1
    assert ledger_matches_balance(engine, customer["account_id"])
    event = recorded_events("loan_repayment")[0]
    assert event["properties"] == {"product_code": "car", "result": "paid"}
    assert event["source"] == "batch"


def test_due_overdue(client, make_user, engine, sink):
    customer, app_id = approved_loan(client, make_user)
    first = installments(engine, app_id)[0]
    set_balance(engine, customer["account_id"], first.amount - 1)

    result = run_repayments(engine, sink, first.due_date)

    assert (result.paid, result.overdue) == (0, 1)
    assert installments(engine, app_id)[0].status == "overdue"
    assert balance(engine, customer["account_id"]) == first.amount - 1
    assert repayment_ledger_count(engine, customer["account_id"]) == 0
    assert results(engine) == ["overdue"]


def test_overdue_auto_recovered(client, make_user, engine, sink):
    customer, app_id = approved_loan(client, make_user)
    first = installments(engine, app_id)[0]
    set_balance(engine, customer["account_id"], 0)
    run_repayments(engine, sink, first.due_date)
    set_balance(engine, customer["account_id"], first.amount)

    result = run_repayments(engine, sink, first.due_date)

    assert result.recovered == 1
    assert installments(engine, app_id)[0].status == "paid"
    assert repayment_ledger_count(engine, customer["account_id"]) == 1
    assert results(engine) == ["overdue", "auto_recovered"]


def test_overdue_retry_still_short_is_skipped(client, make_user, engine, sink):
    customer, app_id = approved_loan(client, make_user)
    first = installments(engine, app_id)[0]
    set_balance(engine, customer["account_id"], 0)
    run_repayments(engine, sink, first.due_date)

    result = run_repayments(engine, sink, first.due_date)

    assert (result.paid, result.overdue, result.recovered, result.skipped) == (0, 0, 0, 1)
    assert results(engine) == ["overdue"]


def test_oldest_first_stops_when_short(client, make_user, engine, sink):
    customer, app_id = approved_loan(client, make_user)
    rows = installments(engine, app_id)
    set_balance(engine, customer["account_id"], 0)
    run_repayments(engine, sink, rows[1].due_date)
    set_balance(engine, customer["account_id"], rows[0].amount)

    run_repayments(engine, sink, rows[1].due_date)

    assert [r.status for r in installments(engine, app_id)[:3]] == ["paid", "overdue", "scheduled"]
    assert balance(engine, customer["account_id"]) == 0


def test_no_manual_overdue_payment_api(client, make_user, engine):
    """연체금 직접 납부 API는 없다. 연체는 다음 상환 배치가 자동으로 다시 빼 간다."""
    _, app_id = approved_loan(client, make_user)

    response = client.post(f"/api/v1/loans/me/{app_id}/repayments", json={"installment_count": 1})

    assert response.status_code in (404, 405)


def test_last_installment_marks_repaid(client, make_user, engine, sink):
    customer, app_id = approved_loan(client, make_user, amount=1_000_000, term=12)
    rows = installments(engine, app_id)
    set_balance(engine, customer["account_id"], sum(r.amount for r in rows))

    result = run_repayments(engine, sink, rows[-1].due_date)

    assert result.paid == 12
    assert {r.status for r in installments(engine, app_id)} == {"paid"}
    with engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM loan_applications WHERE id = :i"), {"i": app_id}).scalar()
    assert status == "repaid"
    assert balance(engine, customer["account_id"]) == 0
    assert ledger_matches_balance(engine, customer["account_id"])


def test_all_overdue_recovered_marks_repaid(client, make_user, engine, sink):
    customer, app_id = approved_loan(client, make_user, amount=1_000_000, term=12)
    rows = installments(engine, app_id)
    set_balance(engine, customer["account_id"], 0)
    run_repayments(engine, sink, rows[-1].due_date)
    assert {r.status for r in installments(engine, app_id)} == {"overdue"}
    set_balance(engine, customer["account_id"], sum(r.amount for r in rows))

    result = run_repayments(engine, sink, rows[-1].due_date)

    assert result.recovered == 12
    with engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM loan_applications WHERE id = :i"), {"i": app_id}).scalar()
    assert status == "repaid"
    assert balance(engine, customer["account_id"]) == 0
