from fastapi import APIRouter, Depends, Query, Request

from app.api.admin.schemas import PendingItem, ReviewResponse
from app.api.loans import service
from app.core.deps import CurrentUser, require_employee

router = APIRouter(prefix="/admin/loans", tags=["admin"])


@router.get("/pending", response_model=list[PendingItem])
def pending(request: Request, limit: int = Query(50, ge=1, le=100), user: CurrentUser = Depends(require_employee)):
    return service.pending(request.app.state.engine, limit)


@router.post("/{application_id}/approve", response_model=ReviewResponse)
def approve(application_id: int, request: Request, user: CurrentUser = Depends(require_employee)):
    return service.review(request.app.state.engine, request, user.id, application_id, approve=True)


@router.post("/{application_id}/reject", response_model=ReviewResponse)
def reject(application_id: int, request: Request, user: CurrentUser = Depends(require_employee)):
    return service.review(request.app.state.engine, request, user.id, application_id, approve=False)
