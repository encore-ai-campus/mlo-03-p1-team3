from datetime import datetime

from pydantic import BaseModel, field_serializer

from app.core.time import kst_iso


class AccountResponse(BaseModel):
    account_number: str
    balance: int


class LedgerItem(BaseModel):
    transaction_id: str
    entry_type: str
    amount: int
    balance_after: int
    created_at: datetime

    @field_serializer("created_at")
    def _kst(self, value: datetime) -> str:
        return kst_iso(value)



class LedgerResponse(BaseModel):
    items: list[LedgerItem]
    limit: int
    offset: int
