import uuid

from fastapi import Request
from sqlalchemy.engine import Connection, Engine

from app.api.accounts.service import lock_customer_account, move_money
from app.api.events.service import EventSink, amount_band, record, transaction
from app.api.loans import repository
from app.api.loans.calc import due_dates, monthly_installment, schedule
from app.core.errors import AppError
from app.core.time import kst_today, utc_now
from app.db.mariadb import translate_db_errors, with_deadlock_retry


def products(engine: Engine) -> list[dict]:
    with engine.connect() as conn:
        return repository.list_products(conn)


def apply(conn: Connection, request: Request, user_id: int, code: str, amount: int, term: int) -> dict:
    product = repository.find_product(conn, code)
    if product is None:
        raise AppError(404, "product_not_found", "대출 상품을 찾을 수 없습니다")
    if not product["min_amount"] <= amount <= product["max_amount"]:
        raise AppError(422, "loan_amount_out_of_range",
                       f"{product['min_amount']:,}원 ~ {product['max_amount']:,}원 사이로 신청해 주세요")
    if amount % product["amount_step"] != 0:
        raise AppError(422, "invalid_loan_amount", f"{product['amount_step']:,}원 단위로 신청해 주세요")
    if term not in product["term_options"]:
        raise AppError(422, "invalid_loan_term", "선택할 수 없는 기간입니다")

    # 같은 고객의 신청이 동시에 와도 하나씩 처리되도록 계좌를 잠근 뒤 진행 중 대출을 확인한다.
    lock_customer_account(conn, user_id)
    if repository.has_active(conn, user_id):
        raise AppError(409, "active_loan_exists", "진행 중인 대출이 있습니다")

    installment = monthly_installment(amount, term)
    application_id = repository.insert_application(conn, user_id, product, amount, term, installment)
    record(conn, request, "loan_application", "success", "completed",
           {"product_code": code, "term_months": term, "amount_band": amount_band(amount)})
    return {"application_id": application_id, "status": "pending", "monthly_installment": installment}


def my_loans(engine: Engine, user_id: int) -> list[dict]:
    with engine.connect() as conn:
        result = []
        for app in repository.list_by_user(conn, user_id):
            installments = [{"number": r["installment_number"], **{k: r[k] for k in (
                "due_date", "amount", "status")}}
                for r in repository.list_repayments(conn, app["id"])]
            result.append({"application_id": app["id"], **{k: app[k] for k in (
                "product_code", "status", "principal_amount", "term_months", "monthly_installment")}, "installments": installments})
        return result


def pending(engine: Engine, limit: int) -> list[dict]:
    with engine.connect() as conn:
        return [dict(r, is_employed=bool(r["is_employed"])) for r in repository.list_pending(conn, limit)]


def review(engine: Engine, request: Request, reviewer_id: int, application_id: int, approve: bool) -> dict:
    """승인·반려를 한 트랜잭션으로 처리한다. 잠금 순서: 신청 → 계좌."""

    def _once() -> dict:
        with transaction(engine, request.app.state.events) as conn:
            loan = repository.lock_application(conn, application_id)
            if loan is None:
                raise AppError(404, "application_not_found", "대출 신청을 찾을 수 없습니다")
            if loan["status"] != "pending":
                raise AppError(409, "application_not_pending", "이미 심사가 끝난 신청입니다")
            status = "repaying" if approve else "rejected"
            if approve:
                _disburse(conn, loan)
            repository.mark_reviewed(conn, application_id, status, reviewer_id, utc_now(), approve)
            record(conn, request, "loan_review", "success", "approved" if approve else "rejected",
                   {"product_code": loan["product_code"], "term_months": loan["term_months"],
                    "amount_band": amount_band(loan["principal_amount"])})
            return {"status": status}

    with translate_db_errors():
        return with_deadlock_retry(_once)


def _disburse(conn: Connection, loan) -> None:
    """대출금을 고객 계좌에 넣고 승인일 기준 상환 회차를 만든다."""
    account = lock_customer_account(conn, loan["user_id"])
    principal, months = loan["principal_amount"], loan["term_months"]
    move_money(conn, account["id"], principal, "loan_disbursement", str(uuid.uuid4()))
    repository.insert_repayments(conn, loan["id"], [
        {"n": number, "d": d, "m": amount}
        for number, (amount, d) in enumerate(zip(schedule(principal, months), due_dates(kst_today(), months),
                                                 strict=True), start=1)
    ])


def _pay_installment(conn: Connection, account_id: int, installment, now) -> None:
    move_money(conn, account_id, -installment["amount"], "loan_repayment", str(uuid.uuid4()))
    repository.mark_installment(conn, installment["id"], "paid", now)


def _close_if_repaid(conn: Connection, application_id: int) -> str:
    if repository.has_unpaid(conn, application_id):
        return "repaying"
    repository.set_status(conn, application_id, "repaid")
    return "repaid"


def repay_due(engine: Engine, sink: EventSink, application_id: int, as_of) -> dict:
    """한 대출의 기한이 된 회차를 오래된 것부터 출금한다. 잠금 순서: 신청 → 회차 → 계좌.

    잔액이 모자라면 그 회차부터 출금을 멈춘다. 새로 기한이 된 회차는 overdue로 바꾸고,
    이미 연체인 회차는 그대로 둔다(skipped). 돌려주는 값: {paid, overdue, recovered, skipped}.
    """
    counts = {"paid": 0, "overdue": 0, "recovered": 0, "skipped": 0}
    with transaction(engine, sink) as conn:
        loan = repository.lock_application(conn, application_id)
        if loan is None or loan["status"] != "repaying":
            return counts
        rows = repository.lock_installments(conn, application_id, ("scheduled", "overdue"), as_of)
        if not rows:
            return counts
        account = lock_customer_account(conn, loan["user_id"])
        balance, now, short = account["balance"], utc_now(), False
        for row in rows:
            was_overdue = row["status"] == "overdue"
            if not short and balance >= row["amount"]:
                _pay_installment(conn, account["id"], row, now)
                balance -= row["amount"]
                result = "auto_recovered" if was_overdue else "paid"
                counts["recovered" if was_overdue else "paid"] += 1
            else:
                short = True
                if was_overdue:
                    counts["skipped"] += 1
                    continue
                repository.mark_installment(conn, row["id"], "overdue", now)
                result = "overdue"
                counts["overdue"] += 1
            record(conn, None, "loan_repayment", "failure" if result == "overdue" else "success",
                   "insufficient_funds" if result == "overdue" else "completed",
                   {"product_code": loan["product_code"], "result": result}, source="batch")
        _close_if_repaid(conn, application_id)
    return counts
