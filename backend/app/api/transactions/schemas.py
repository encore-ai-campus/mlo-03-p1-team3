from pydantic import BaseModel, StrictInt


class AmountRequest(BaseModel):
    amount: StrictInt


class MoneyResponse(BaseModel):
    transaction_id: str
    balance: int
