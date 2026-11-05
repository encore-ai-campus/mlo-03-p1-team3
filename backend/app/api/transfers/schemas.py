from pydantic import BaseModel, Field, StrictInt


class LookupRequest(BaseModel):
    query: str = Field(min_length=1, max_length=20)


class LookupResponse(BaseModel):
    name: str


class TransferRequest(BaseModel):
    recipient: str = Field(min_length=1, max_length=20, description="받는 사람 조회 때 입력한 전화번호 또는 계좌번호")
    amount: StrictInt


class TransferResponse(BaseModel):
    transaction_id: str
    balance: int
