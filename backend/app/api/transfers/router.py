from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from app.api.events.service import amount_band
from app.api.transfers import service
from app.api.transfers.schemas import LookupRequest, LookupResponse, TransferRequest, TransferResponse
from app.core.deps import run_customer, run_customer_read, session_token
from app.core.money import run_money

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.post("/recipient-lookup", response_model=LookupResponse)
async def recipient_lookup(body: LookupRequest, request: Request, token: str = Depends(session_token)):
    return await run_in_threadpool(
        run_customer_read, request, token, lambda conn, user: service.lookup_on(conn, body.query),
    )


@router.post("", response_model=TransferResponse)
async def transfer(body: TransferRequest, request: Request, token: str = Depends(session_token)):
    props = {"amount_band": amount_band(max(body.amount, 0))}
    return await run_in_threadpool(
        run_customer, request, token,
        lambda user: run_money(
            request, "transfer", props,
            lambda conn: service.transfer(conn, request, user.id, body.recipient, body.amount),
        ),
    )
