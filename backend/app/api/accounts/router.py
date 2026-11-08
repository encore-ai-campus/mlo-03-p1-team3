from fastapi import APIRouter, Depends, Query, Request
from starlette.concurrency import run_in_threadpool

from app.api.accounts import repository, service
from app.api.accounts.schemas import AccountResponse, LedgerResponse
from app.core.deps import CurrentUser, require_customer, run_customer_read, session_token

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("/me", response_model=AccountResponse)
async def my_account(request: Request, token: str = Depends(session_token)):
    account = await run_in_threadpool(
        run_customer_read, request, token, lambda conn, user: repository.find_by_user(conn, user.id),
    )
    if account is None:
        raise service.account_not_found()
    return AccountResponse(account_number=account["account_number"], balance=account["balance"])


@router.get("/me/ledger", response_model=LedgerResponse)
def my_ledger(request: Request, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0, le=10_000),
              user: CurrentUser = Depends(require_customer)):
    rows = service.my_ledger(request.app.state.engine, user.id, limit, offset)
    return LedgerResponse(items=[dict(r) for r in rows], limit=limit, offset=offset)
