from pydantic import BaseModel


class PendingItem(BaseModel):
    application_id: int
    product_code: str
    amount: int
    product_max_amount: int
    term_months: int
    is_employed: bool


class ReviewResponse(BaseModel):
    status: str
