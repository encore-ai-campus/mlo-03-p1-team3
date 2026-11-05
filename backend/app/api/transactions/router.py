from fastapi import APIRouter, Depends, Request

from app.api.events.service import amount_band
from app.api.transactions import service
from app.api.transactions.schemas import AmountRequest, MoneyResponse
from app.core.deps import CurrentUser, require_customer
from app.core.money import run_money

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _run(kind: str, body: AmountRequest, request: Request, user: CurrentUser):
    props = {"amount_band": amount_band(max(body.amount, 0))}
    return run_money(request, kind, props, lambda conn: service.cash(conn, request, user.id, body.amount, kind))


@router.post("/deposit", response_model=MoneyResponse)
def deposit(body: AmountRequest, request: Request, user: CurrentUser = Depends(require_customer)):
    return _run("deposit", body, request, user)


@router.post("/withdrawal", response_model=MoneyResponse)
def withdrawal(body: AmountRequest, request: Request, user: CurrentUser = Depends(require_customer)):
    return _run("withdrawal", body, request, user)
