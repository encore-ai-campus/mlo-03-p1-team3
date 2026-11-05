from pydantic import BaseModel, StrictInt


class CardResponse(BaseModel):
    card_last4: str


class MerchantItem(BaseModel):
    id: int
    name: str
    category: str
    region: str


class PaymentRequest(BaseModel):
    merchant_id: StrictInt
    amount: StrictInt


class PaymentResponse(BaseModel):
    transaction_id: str
    balance: int
