from datetime import UTC, datetime, timedelta, timezone

import pytest
from bson import BSON
from bson.codec_options import CodecOptions
from pydantic import ValidationError

from app.api.events.schemas import BankingEvent

# 이벤트 목록은 구현 정의표와 별도로 두어 누락·오타를 검출한다.
GROUPS = {
    "MEMBER": "MEMBER_REGISTERED LOGIN_REQUESTED LOGIN_SUCCEEDED LOGIN_FAILED LOGOUT_SUCCEEDED",
    "ACCOUNT": "ACCOUNT_CREATED ACCOUNT_VIEWED TRANSACTION_HISTORY_VIEWED DEPOSIT_REQUESTED "
               "DEPOSIT_SUCCEEDED DEPOSIT_FAILED WITHDRAWAL_REQUESTED WITHDRAWAL_SUCCEEDED "
               "WITHDRAWAL_FAILED WITHDRAWAL_LIMIT_EXCEEDED",
    "TRANSFER": "TRANSFER_REQUESTED TRANSFER_SUCCEEDED TRANSFER_FAILED TRANSFER_LIMIT_EXCEEDED",
    "CARD": "CARD_ISSUANCE_REQUESTED CARD_ISSUED CARD_VIEWED CARD_PAYMENT_APPROVED CARD_PAYMENT_DECLINED",
    "LOAN": "LOAN_PRODUCT_VIEWED LOAN_LIMIT_INQUIRED LOAN_APPLIED LOAN_APPROVED LOAN_REJECTED "
            "LOAN_DISBURSED LOAN_VIEWED LOAN_REPAYMENT_REQUESTED LOAN_REPAYMENT_SUCCEEDED "
            "LOAN_REPAYMENT_FAILED LOAN_FULLY_REPAID",
}
# 총 35개: MEMBER 5 + ACCOUNT 10 + TRANSFER 4 + CARD 5 + LOAN 11.
CASES = [(category, name) for category, names in GROUPS.items() for name in names.split()]


def payload_for(name):
    if name == "LOGOUT_SUCCEEDED":
        return {}
    if name == "MEMBER_REGISTERED" or name.startswith("LOGIN_"):
        return {"login_method": "PASSWORD"}
    if name in {"ACCOUNT_CREATED", "ACCOUNT_VIEWED", "TRANSACTION_HISTORY_VIEWED"}:
        return {"account_id": "acc_1"}
    if name.startswith(("DEPOSIT_", "WITHDRAWAL_")):
        payload = {"transaction_id": "txn_1", "account_id": "acc_1", "amount": 100,
                   "transaction_method": "ATM"}
        if name.endswith("SUCCEEDED"):
            payload["balance_after"] = 200
        return payload
    if name.startswith("TRANSFER_"):
        return {"transaction_id": "txn_1", "sender_account_id": "acc_1",
                "receiver_account_id": "acc_2", "amount": 100, "is_new_recipient": True}
    if name == "CARD_ISSUANCE_REQUESTED":
        return {"account_id": "acc_1"}
    if name == "CARD_ISSUED":
        return {"account_id": "acc_1", "card_id": "card_1"}
    if name == "CARD_VIEWED":
        return {"card_id": "card_1"}
    if name.startswith("CARD_PAYMENT_"):
        return {"payment_id": "pay_1", "card_id": "card_1", "merchant_id": "merchant_1",
                "merchant_category": "ONLINE_SHOPPING", "amount": 100,
                "payment_channel": "ONLINE", "merchant_country": "US"}
    if name in {"LOAN_PRODUCT_VIEWED", "LOAN_LIMIT_INQUIRED"}:
        return {"product_id": "product_1"}
    if name in {"LOAN_APPLIED", "LOAN_APPROVED", "LOAN_REJECTED"}:
        payload = {"application_id": "app_1", "product_id": "product_1", "requested_amount": 100,
                   "loan_status": name.removeprefix("LOAN_")}
        if name == "LOAN_APPROVED":
            payload["approved_amount"] = 80
        return payload
    if name == "LOAN_DISBURSED" or name.startswith("LOAN_REPAYMENT_"):
        return {"loan_id": "loan_1", "transaction_id": "txn_1", "amount": 80}
    return {"loan_id": "loan_1"}


def status_for(name):
    if name.endswith("REQUESTED"):
        return "PENDING"
    if name.endswith(("FAILED", "EXCEEDED", "DECLINED", "REJECTED")):
        return "FAILURE"
    return "SUCCESS"


def event_data(name="TRANSFER_SUCCEEDED"):
    category = next(category for category, event in CASES if event == name)
    status = status_for(name)
    return {
        "category": category, "event_type": name,
        "occurred_at": "2026-11-03T08:30:00Z", "collected_at": "2026-11-03T08:30:01Z",
        "request_id": "req_1", "source": {"channel": "WEB"}, "payload": payload_for(name),
        "result": {"status": status, "failure_code": "DECLINED" if status == "FAILURE" else None},
    }


@pytest.mark.parametrize(("category", "name"), CASES)
def test_all_event_contracts(category, name):
    event = BankingEvent.model_validate(event_data(name))
    assert event.category == category
    assert event.result.status == status_for(name)
    assert BSON.encode(event.to_mongo_document())


@pytest.mark.parametrize(("category", "name"), CASES)
def test_wrong_category_and_status_rejected(category, name):
    data = event_data(name)
    data["category"] = "LOAN" if category != "LOAN" else "MEMBER"
    with pytest.raises(ValidationError):
        BankingEvent.model_validate(data)
    data = event_data(name)
    data["result"] = {"status": "SUCCESS" if status_for(name) != "SUCCESS" else "PENDING"}
    with pytest.raises(ValidationError):
        BankingEvent.model_validate(data)


def test_event_registry_is_exact():
    from app.api.events.schemas import EVENT_DEFINITIONS, EventType

    assert len(CASES) == 35
    assert set(EVENT_DEFINITIONS) == {name for _, name in CASES} == set(EventType)


@pytest.mark.parametrize("name", ["MEMBER_SUCCEEDED", "ACCOUNT_SUCCEEDED", "CARD_PAYMENT_SUCCEEDED",
                                  "LOAN_SUCCEEDED", "LOGIN_APPROVED", "TRANSFER_UNKNOWN"])
def test_unknown_events_rejected(name):
    data = event_data()
    data["event_type"] = name
    with pytest.raises(ValidationError):
        BankingEvent.model_validate(data)


def test_bson_round_trip_and_utc_normalization():
    data = event_data()
    data["occurred_at"] = datetime(2026, 11, 3, 17, 30, tzinfo=timezone(timedelta(hours=9)))
    event = BankingEvent.model_validate(data)
    doc = event.to_mongo_document()
    decoded = BSON(BSON.encode(doc)).decode(codec_options=CodecOptions(tz_aware=True))
    assert event.occurred_at == datetime(2026, 11, 3, 8, 30, tzinfo=UTC)
    assert decoded["occurred_at"] == event.occurred_at
    assert isinstance(decoded["collected_at"], datetime)
    assert type(doc["event_type"]) is str
    assert doc["result"]["failure_code"] is None
    assert "user_id" not in doc


@pytest.mark.parametrize("value", [datetime(2026, 11, 3), "2026-11-03T08:30:00", 123, {"$date": "2026-11-03"}])
@pytest.mark.parametrize("field", ["occurred_at", "collected_at"])
def test_invalid_or_naive_time_rejected(field, value):
    data = event_data()
    data[field] = value
    with pytest.raises(ValidationError):
        BankingEvent.model_validate(data)


@pytest.mark.parametrize("amount", [-1, 1.5, True, "100", 2**63])
def test_invalid_money_rejected(amount):
    data = event_data()
    data["payload"]["amount"] = amount
    with pytest.raises(ValidationError):
        BankingEvent.model_validate(data)


@pytest.mark.parametrize("name", ["DEPOSIT_REQUESTED", "DEPOSIT_FAILED", "WITHDRAWAL_LIMIT_EXCEEDED"])
def test_unconfirmed_balance_rejected(name):
    data = event_data(name)
    assert "balance_after" not in BankingEvent.model_validate(data).to_mongo_document()["payload"]
    data["payload"]["balance_after"] = 0
    with pytest.raises(ValidationError):
        BankingEvent.model_validate(data)


@pytest.mark.parametrize("name", ["LOAN_APPLIED", "LOAN_REJECTED"])
def test_unconfirmed_approval_rejected(name):
    data = event_data(name)
    assert "approved_amount" not in BankingEvent.model_validate(data).to_mongo_document()["payload"]
    data["payload"]["approved_amount"] = 80
    with pytest.raises(ValidationError):
        BankingEvent.model_validate(data)


@pytest.mark.parametrize("name", ["DEPOSIT_SUCCEEDED", "WITHDRAWAL_SUCCEEDED", "LOAN_APPROVED"])
def test_success_requires_confirmed_fields(name):
    data = event_data(name)
    del data["payload"]["approved_amount" if name == "LOAN_APPROVED" else "balance_after"]
    with pytest.raises(ValidationError):
        BankingEvent.model_validate(data)


@pytest.mark.parametrize("change", [
    {"result": {"status": "FAILURE"}},
    {"result": {"status": "SUCCESS", "failure_code": "DECLINED"}},
    {"schema_version": True}, {"schema_version": 2}, {"unexpected": "value"},
    {"payload": {"card_id": "card_1"}},
])
def test_inconsistent_contract_rejected(change):
    data = event_data()
    data.update(change)
    with pytest.raises(ValidationError):
        BankingEvent.model_validate(data)


@pytest.mark.parametrize(("category", "name"), CASES)
def test_required_payload_fields_and_unknown_fields(category, name):
    data = event_data(name)
    data["payload"]["phone_number"] = "fake"
    with pytest.raises(ValidationError):
        BankingEvent.model_validate(data)
    # 각 이벤트의 최소 payload에서 필드를 하나씩 빼 필수 조건을 확인한다.
    for field in payload_for(name):
        if field in {"loan_status"}:
            continue
        data = event_data(name)
        del data["payload"][field]
        with pytest.raises(ValidationError):
            BankingEvent.model_validate(data)


def test_loan_status_cannot_disagree_with_event():
    data = event_data("LOAN_APPROVED")
    data["payload"]["loan_status"] = "REJECTED"
    with pytest.raises(ValidationError):
        BankingEvent.model_validate(data)


def test_distinct_event_ids_and_shared_transaction():
    events = [BankingEvent.model_validate(event_data("TRANSFER_" + phase))
              for phase in ["REQUESTED", "SUCCEEDED", "FAILED"]]
    assert len({e.event_id for e in events}) == 3
    assert {e.payload.transaction_id for e in events} == {"txn_1"}


def test_payload_model_instance_cannot_bypass_event_contract():
    other = BankingEvent.model_validate(event_data("CARD_VIEWED"))
    data = event_data()
    data["payload"] = other.payload
    with pytest.raises(ValidationError):
        BankingEvent.model_validate(data)


@pytest.mark.parametrize("event_type", [[], {}, None, 123])
def test_malformed_event_type_is_validation_error(event_type):
    data = event_data()
    data["event_type"] = event_type
    with pytest.raises(ValidationError):
        BankingEvent.model_validate(data)


def test_member_failure_reason_and_optional_context():
    data = event_data("LOGIN_FAILED")
    data["payload"].update(mfa_used=False, is_new_device=True, failure_reason="INVALID_CREDENTIALS")
    assert BankingEvent.model_validate(data).payload.failure_reason == "INVALID_CREDENTIALS"
    data = event_data("LOGIN_SUCCEEDED")
    data["payload"]["failure_reason"] = "INVALID_CREDENTIALS"
    with pytest.raises(ValidationError):
        BankingEvent.model_validate(data)


def test_already_constructed_model_is_revalidated():
    original = BankingEvent.model_validate(event_data())
    invalid = original.model_copy(update={"category": "MEMBER"})
    with pytest.raises(ValidationError):
        BankingEvent.model_validate(invalid)
