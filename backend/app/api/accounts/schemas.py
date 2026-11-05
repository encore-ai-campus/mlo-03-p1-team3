from datetime import datetime

from pydantic import BaseModel, field_serializer


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
    def _utc(self, value: datetime) -> str:
        # DB는 UTC를 시간대 없이 저장한다. 브라우저가 한국 시간으로 잘못 읽지 않게 Z(UTC)를 붙인다.
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")


class LedgerResponse(BaseModel):
    items: list[LedgerItem]
    limit: int
    offset: int
