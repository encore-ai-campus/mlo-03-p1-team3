"""새 분석 이벤트 계약. 기존 events_bronze 기록 경로에는 아직 연결하지 않는다."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

BANKING_DATABASE = "banking"
BANKING_COLLECTION = "banking_events"
Identifier = Annotated[str, Field(min_length=1, pattern=r"\S")]
Money = Annotated[StrictInt, Field(ge=0, le=2**63 - 1)]
UtcDatetime = Annotated[AwareDatetime, AfterValidator(lambda value: value.astimezone(UTC))]


class EventModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class EventSource(EventModel):
    service: Identifier = "banking-api"
    channel: Identifier


class EventClient(EventModel):
    ip_address: str | None = None
    device_id: Identifier | None = None
    device_type: Identifier | None = None
    country: Annotated[str, Field(pattern=r"^[A-Z]{2}$")] | None = None


class EventResult(EventModel):
    status: Literal["PENDING", "SUCCESS", "FAILURE"]
    failure_code: Identifier | None = None

    @model_validator(mode="after")
    def check_failure(self):
        if (self.status == "FAILURE") != (self.failure_code is not None):
            raise ValueError("failure_code is required only for FAILURE")
        return self


class EmptyPayload(EventModel):
    """로그아웃은 공통 헤더의 분석용 세션 식별자를 사용한다."""


class MemberPayload(EventModel):
    login_method: Identifier
    mfa_used: StrictBool | None = None
    is_new_device: StrictBool | None = None
    failure_reason: Identifier | None = None


class AccountReferencePayload(EventModel):
    account_id: Identifier


class AccountPayload(AccountReferencePayload):
    transaction_id: Identifier
    amount: Money
    currency: Literal["KRW"] = "KRW"
    transaction_method: Identifier


class AccountSucceededPayload(AccountPayload):
    balance_after: Money


class TransferPayload(EventModel):
    transaction_id: Identifier
    sender_account_id: Identifier
    receiver_account_id: Identifier
    receiver_bank_id: Identifier | None = None
    amount: Money
    currency: Literal["KRW"] = "KRW"
    is_new_recipient: StrictBool


class CardReferencePayload(EventModel):
    card_id: Identifier


class CardIssuancePayload(EventModel):
    account_id: Identifier


class CardIssuedPayload(CardIssuancePayload):
    card_id: Identifier


class CardPayload(CardReferencePayload):
    payment_id: Identifier
    merchant_id: Identifier
    merchant_category: Identifier
    amount: Money
    currency: Literal["KRW"] = "KRW"
    payment_channel: Identifier
    merchant_country: Annotated[str, Field(pattern=r"^[A-Z]{2}$")]


class LoanProductPayload(EventModel):
    product_id: Identifier


class LoanPayload(LoanProductPayload):
    application_id: Identifier
    loan_id: Identifier | None = None
    requested_amount: Money
    currency: Literal["KRW"] = "KRW"
    loan_status: Literal["APPLIED", "APPROVED", "REJECTED"]


class LoanApprovedPayload(LoanPayload):
    approved_amount: Money


class LoanReferencePayload(EventModel):
    loan_id: Identifier


class LoanTransactionPayload(LoanReferencePayload):
    transaction_id: Identifier
    amount: Money
    currency: Literal["KRW"] = "KRW"


class EventType(StrEnum):
    MEMBER_REGISTERED = "MEMBER_REGISTERED"
    LOGIN_REQUESTED = "LOGIN_REQUESTED"
    LOGIN_SUCCEEDED = "LOGIN_SUCCEEDED"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT_SUCCEEDED = "LOGOUT_SUCCEEDED"
    ACCOUNT_CREATED = "ACCOUNT_CREATED"
    ACCOUNT_VIEWED = "ACCOUNT_VIEWED"
    TRANSACTION_HISTORY_VIEWED = "TRANSACTION_HISTORY_VIEWED"
    DEPOSIT_REQUESTED = "DEPOSIT_REQUESTED"
    DEPOSIT_SUCCEEDED = "DEPOSIT_SUCCEEDED"
    DEPOSIT_FAILED = "DEPOSIT_FAILED"
    WITHDRAWAL_REQUESTED = "WITHDRAWAL_REQUESTED"
    WITHDRAWAL_SUCCEEDED = "WITHDRAWAL_SUCCEEDED"
    WITHDRAWAL_FAILED = "WITHDRAWAL_FAILED"
    WITHDRAWAL_LIMIT_EXCEEDED = "WITHDRAWAL_LIMIT_EXCEEDED"
    TRANSFER_REQUESTED = "TRANSFER_REQUESTED"
    TRANSFER_SUCCEEDED = "TRANSFER_SUCCEEDED"
    TRANSFER_FAILED = "TRANSFER_FAILED"
    TRANSFER_LIMIT_EXCEEDED = "TRANSFER_LIMIT_EXCEEDED"
    CARD_ISSUANCE_REQUESTED = "CARD_ISSUANCE_REQUESTED"
    CARD_ISSUED = "CARD_ISSUED"
    CARD_VIEWED = "CARD_VIEWED"
    CARD_PAYMENT_APPROVED = "CARD_PAYMENT_APPROVED"
    CARD_PAYMENT_DECLINED = "CARD_PAYMENT_DECLINED"
    LOAN_PRODUCT_VIEWED = "LOAN_PRODUCT_VIEWED"
    LOAN_LIMIT_INQUIRED = "LOAN_LIMIT_INQUIRED"
    LOAN_APPLIED = "LOAN_APPLIED"
    LOAN_APPROVED = "LOAN_APPROVED"
    LOAN_REJECTED = "LOAN_REJECTED"
    LOAN_DISBURSED = "LOAN_DISBURSED"
    LOAN_VIEWED = "LOAN_VIEWED"
    LOAN_REPAYMENT_REQUESTED = "LOAN_REPAYMENT_REQUESTED"
    LOAN_REPAYMENT_SUCCEEDED = "LOAN_REPAYMENT_SUCCEEDED"
    LOAN_REPAYMENT_FAILED = "LOAN_REPAYMENT_FAILED"
    LOAN_FULLY_REPAID = "LOAN_FULLY_REPAID"


Category = Literal["MEMBER", "ACCOUNT", "TRANSFER", "CARD", "LOAN"]
Status = Literal["PENDING", "SUCCESS", "FAILURE"]
Payload = (
    EmptyPayload | MemberPayload | AccountReferencePayload | AccountPayload | AccountSucceededPayload
    | TransferPayload | CardReferencePayload | CardIssuancePayload | CardIssuedPayload | CardPayload
    | LoanProductPayload | LoanPayload | LoanApprovedPayload | LoanReferencePayload | LoanTransactionPayload
)


@dataclass(frozen=True)
class EventDefinition:
    category: Category
    status: Status
    payload_model: type[EventModel]
    loan_status: str | None = None


# 접두사·접미사로 추측하지 않고 명시적인 계약 한 곳에서 관리한다.
# LOAN_APPLIED의 SUCCESS는 신청 접수 성공이며 대출 승인 성공이 아니다.
# CARD_PAYMENT_APPROVED는 결제 승인만 뜻하며 매입·정산을 뜻하지 않는다.
EVENT_DEFINITIONS = {
    EventType.MEMBER_REGISTERED: EventDefinition("MEMBER", "SUCCESS", MemberPayload),
    EventType.LOGIN_REQUESTED: EventDefinition("MEMBER", "PENDING", MemberPayload),
    EventType.LOGIN_SUCCEEDED: EventDefinition("MEMBER", "SUCCESS", MemberPayload),
    EventType.LOGIN_FAILED: EventDefinition("MEMBER", "FAILURE", MemberPayload),
    EventType.LOGOUT_SUCCEEDED: EventDefinition("MEMBER", "SUCCESS", EmptyPayload),
    EventType.ACCOUNT_CREATED: EventDefinition("ACCOUNT", "SUCCESS", AccountReferencePayload),
    EventType.ACCOUNT_VIEWED: EventDefinition("ACCOUNT", "SUCCESS", AccountReferencePayload),
    EventType.TRANSACTION_HISTORY_VIEWED: EventDefinition("ACCOUNT", "SUCCESS", AccountReferencePayload),
    EventType.DEPOSIT_REQUESTED: EventDefinition("ACCOUNT", "PENDING", AccountPayload),
    EventType.DEPOSIT_SUCCEEDED: EventDefinition("ACCOUNT", "SUCCESS", AccountSucceededPayload),
    EventType.DEPOSIT_FAILED: EventDefinition("ACCOUNT", "FAILURE", AccountPayload),
    EventType.WITHDRAWAL_REQUESTED: EventDefinition("ACCOUNT", "PENDING", AccountPayload),
    EventType.WITHDRAWAL_SUCCEEDED: EventDefinition("ACCOUNT", "SUCCESS", AccountSucceededPayload),
    EventType.WITHDRAWAL_FAILED: EventDefinition("ACCOUNT", "FAILURE", AccountPayload),
    EventType.WITHDRAWAL_LIMIT_EXCEEDED: EventDefinition("ACCOUNT", "FAILURE", AccountPayload),
    EventType.TRANSFER_REQUESTED: EventDefinition("TRANSFER", "PENDING", TransferPayload),
    EventType.TRANSFER_SUCCEEDED: EventDefinition("TRANSFER", "SUCCESS", TransferPayload),
    EventType.TRANSFER_FAILED: EventDefinition("TRANSFER", "FAILURE", TransferPayload),
    EventType.TRANSFER_LIMIT_EXCEEDED: EventDefinition("TRANSFER", "FAILURE", TransferPayload),
    EventType.CARD_ISSUANCE_REQUESTED: EventDefinition("CARD", "PENDING", CardIssuancePayload),
    EventType.CARD_ISSUED: EventDefinition("CARD", "SUCCESS", CardIssuedPayload),
    EventType.CARD_VIEWED: EventDefinition("CARD", "SUCCESS", CardReferencePayload),
    EventType.CARD_PAYMENT_APPROVED: EventDefinition("CARD", "SUCCESS", CardPayload),
    EventType.CARD_PAYMENT_DECLINED: EventDefinition("CARD", "FAILURE", CardPayload),
    EventType.LOAN_PRODUCT_VIEWED: EventDefinition("LOAN", "SUCCESS", LoanProductPayload),
    EventType.LOAN_LIMIT_INQUIRED: EventDefinition("LOAN", "SUCCESS", LoanProductPayload),
    EventType.LOAN_APPLIED: EventDefinition("LOAN", "SUCCESS", LoanPayload, "APPLIED"),
    EventType.LOAN_APPROVED: EventDefinition("LOAN", "SUCCESS", LoanApprovedPayload, "APPROVED"),
    EventType.LOAN_REJECTED: EventDefinition("LOAN", "FAILURE", LoanPayload, "REJECTED"),
    EventType.LOAN_DISBURSED: EventDefinition("LOAN", "SUCCESS", LoanTransactionPayload),
    EventType.LOAN_VIEWED: EventDefinition("LOAN", "SUCCESS", LoanReferencePayload),
    EventType.LOAN_REPAYMENT_REQUESTED: EventDefinition("LOAN", "PENDING", LoanTransactionPayload),
    EventType.LOAN_REPAYMENT_SUCCEEDED: EventDefinition("LOAN", "SUCCESS", LoanTransactionPayload),
    EventType.LOAN_REPAYMENT_FAILED: EventDefinition("LOAN", "FAILURE", LoanTransactionPayload),
    EventType.LOAN_FULLY_REPAID: EventDefinition("LOAN", "SUCCESS", LoanReferencePayload),
}


class BankingEvent(EventModel):
    """session_id는 인증 토큰이 아닌 분석용 식별자다. 익명 요청은 ID를 생략할 수 있다.

    입출금·송금·대출 지급·상환은 transaction_id, 카드 결제는 payment_id,
    대출 심사는 application_id로 연결한다. 로그인·카드 발급은 request_id로 연결한다.
    ID를 각 단계에서 유지하는 일은 발행 계층의 책임이다.
    collected_at은 수집 시각이며, 시간 구간 분석은 occurred_at을 사용한다.
    """

    event_id: Identifier = Field(default_factory=lambda: str(uuid4()))
    schema_version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    category: Category
    event_type: EventType
    occurred_at: UtcDatetime
    collected_at: UtcDatetime
    user_id: Identifier | None = None
    session_id: Identifier | None = None
    request_id: Identifier
    source: EventSource
    client: EventClient | None = None
    payload: Payload
    result: EventResult

    @model_validator(mode="before")
    @classmethod
    def parse_payload(cls, data):
        if isinstance(data, dict) and "payload" in data:
            event_type = data.get("event_type")
            definition = EVENT_DEFINITIONS.get(event_type) if isinstance(event_type, str) else None
            if definition is not None:
                data = dict(data)
                payload = data["payload"]
                if isinstance(payload, EventModel):
                    payload = payload.model_dump(exclude_none=True)
                data["payload"] = definition.payload_model.model_validate(payload)
        return data

    @field_validator("occurred_at", "collected_at", mode="before")
    @classmethod
    def require_datetime(cls, value):
        if not isinstance(value, (str, datetime)):
            # Pydantic은 ValueError를 ValidationError로 묶고 TypeError는 그대로 전파한다.
            raise ValueError("time must be an aware datetime or ISO 8601 string")  # noqa: TRY004
        return value

    @model_validator(mode="after")
    def check_contract(self):
        definition = EVENT_DEFINITIONS[self.event_type]
        if self.category != definition.category or self.result.status != definition.status:
            raise ValueError("event_type, category and result.status must agree")
        if type(self.payload) is not definition.payload_model:
            raise ValueError("payload must match event_type")
        if definition.loan_status is not None and self.payload.loan_status != definition.loan_status:
            raise ValueError("loan_status must match event_type")
        if (isinstance(self.payload, MemberPayload) and self.payload.failure_reason is not None
                and self.result.status != "FAILURE"):
            raise ValueError("failure_reason is allowed only for failed member events")
        return self

    def to_mongo_document(self) -> dict:
        """BSON Date용 datetime을 유지하고 미확정 선택 필드는 생략한다."""
        document = self.model_dump(mode="python", exclude_none=True)
        document["event_type"] = self.event_type.value
        document["result"]["failure_code"] = self.result.failure_code
        return document
