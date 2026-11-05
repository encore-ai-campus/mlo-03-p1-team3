import pytest

from app.api.events.service import FORBIDDEN_KEYS, amount_band, build_event


@pytest.mark.parametrize(
    ("amount", "band"),
    [(9_999, "under_10k"), (10_000, "under_100k"), (999_999, "under_1m"), (1_000_000, "over_1m")],
)
def test_amount_band_edges(amount, band):
    assert amount_band(amount) == band


def test_build_event_rejects_forbidden_keys():
    with pytest.raises(ValueError):
        build_event("deposit", "success", "completed", source="api", request_id=None,
                    duration_ms=None, properties={"user_id": 1})


def test_build_event_rejects_nested_forbidden_keys():
    with pytest.raises(ValueError):
        build_event("deposit", "success", "completed", source="api", request_id=None,
                    duration_ms=None, properties={"extra": {"phone_number": "010"}})


def test_build_event_fields():
    event = build_event("deposit", "success", "completed", source="api", request_id="r1",
                        duration_ms=12, properties={"amount_band": "under_10k"})

    assert set(event) == {"event_id", "event_type", "occurred_at", "source", "outcome", "reason",
                          "duration_ms", "request_id", "properties"}
    assert event["occurred_at"].endswith("Z")


def test_forbidden_keys_cover_personal_data():
    assert {"user_id", "phone_number", "account_number", "card_number", "amount", "birth_year"} <= FORBIDDEN_KEYS
