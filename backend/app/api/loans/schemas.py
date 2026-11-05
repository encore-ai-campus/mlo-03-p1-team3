from datetime import date

from pydantic import BaseModel, Field, StrictInt


class ProductItem(BaseModel):
    code: str
    name: str
    min_amount: int
    max_amount: int
    amount_step: int
    term_options: list[int]


class ApplyRequest(BaseModel):
    product_code: str = Field(min_length=1, max_length=16)
    amount: StrictInt
    term_months: StrictInt


class ApplyResponse(BaseModel):
    application_id: int
    status: str
    monthly_installment: int


class InstallmentItem(BaseModel):
    number: int
    due_date: date
    amount: int
    status: str


class MyLoanItem(BaseModel):
    application_id: int
    product_code: str
    status: str
    principal_amount: int
    term_months: int
    monthly_installment: int
    installments: list[InstallmentItem]
