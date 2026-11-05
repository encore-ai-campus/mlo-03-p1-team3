from fastapi import APIRouter, Depends, Request

from app.api.events.service import amount_band
from app.api.loans import service
from app.api.loans.schemas import ApplyRequest, ApplyResponse, MyLoanItem, ProductItem
from app.core.deps import CurrentUser, require_customer
from app.core.money import run_money

router = APIRouter(prefix="/loans", tags=["loans"])


@router.get("/products", response_model=list[ProductItem])
def products(request: Request, user: CurrentUser = Depends(require_customer)):
    return service.products(request.app.state.engine)


@router.post("/applications", response_model=ApplyResponse)
def apply(body: ApplyRequest, request: Request, user: CurrentUser = Depends(require_customer)):
    props = {"product_code": body.product_code, "term_months": body.term_months,
             "amount_band": amount_band(max(body.amount, 0))}
    return run_money(
        request, "loan_application", props,
        lambda conn: service.apply(conn, request, user.id, body.product_code, body.amount, body.term_months),
    )


@router.get("/me", response_model=list[MyLoanItem])
def my_loans(request: Request, user: CurrentUser = Depends(require_customer)):
    return service.my_loans(request.app.state.engine, user.id)
