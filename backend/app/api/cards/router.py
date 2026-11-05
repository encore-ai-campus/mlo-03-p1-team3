from fastapi import APIRouter, Depends, Request

from app.api.cards import service
from app.api.cards.schemas import CardResponse, MerchantItem, PaymentRequest, PaymentResponse
from app.api.events.service import amount_band
from app.core.deps import CurrentUser, require_customer
from app.core.money import run_money

router = APIRouter(tags=["cards"])


@router.get("/cards/me", response_model=CardResponse)
def my_card(request: Request, user: CurrentUser = Depends(require_customer)):
    return service.my_card(request.app.state.engine, user.id)


@router.get("/merchants", response_model=list[MerchantItem])
def merchants(request: Request, user: CurrentUser = Depends(require_customer)):
    return [dict(row) for row in service.merchants(request.app.state.engine)]


@router.post("/cards/payments", response_model=PaymentResponse)
def pay(body: PaymentRequest, request: Request, user: CurrentUser = Depends(require_customer)):
    props = {"amount_band": amount_band(max(body.amount, 0))}
    return run_money(
        request, "card_payment", props,
        lambda conn: service.pay(conn, request, user.id, body.merchant_id, body.amount),
    )
