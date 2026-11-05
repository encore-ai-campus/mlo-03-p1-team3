from concurrent.futures import ThreadPoolExecutor

from app.jobs.repayments import run_repayments
from tests.api.loans.test_repayments import approved_loan, installments, repayment_ledger_count, set_balance
from tests.conftest import ledger_matches_balance


def test_parallel_batch_runs(client, make_user, engine, sink):
    loans = [approved_loan(client, make_user) for _ in range(3)]
    rows = installments(engine, loans[0][1])
    for customer, _ in loans:
        set_balance(engine, customer["account_id"], 10 * rows[0].amount)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: run_repayments(engine, sink, rows[1].due_date), range(2)))

    for customer, app_id in loans:
        assert repayment_ledger_count(engine, customer["account_id"]) == 2
        assert [r.status for r in installments(engine, app_id)[:3]] == ["paid", "paid", "scheduled"]
        assert ledger_matches_balance(engine, customer["account_id"])
