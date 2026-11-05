from fastapi import APIRouter, Depends, Request

from app.api.events.service import amount_band
from app.api.transfers import service
from app.api.transfers.schemas import LookupRequest, LookupResponse, TransferRequest, TransferResponse
from app.core.deps import CurrentUser, require_customer
from app.core.money import run_money

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.post("/recipient-lookup", response_model=LookupResponse)
def recipient_lookup(body: LookupRequest, request: Request, user: CurrentUser = Depends(require_customer)):
    return service.lookup(request.app.state.engine, body.query)


@router.post("", response_model=TransferResponse)
def transfer(body: TransferRequest, request: Request, user: CurrentUser = Depends(require_customer)):
    props = {"amount_band": amount_band(max(body.amount, 0))}
    return run_money(
        request, "transfer", props,
        lambda conn: service.transfer(conn, request, user.id, body.recipient, body.amount),
    )
