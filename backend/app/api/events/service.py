import json
import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pymongo.database import Database
from pymongo.errors import PyMongoError
from sqlalchemy.engine import Connection, Engine

from app.observability.application_log import ApplicationLog

LOG_COLLECTION = "events_bronze"
_PENDING = "podobank_pending_events"
logger = logging.getLogger("app.events")

FORBIDDEN_KEYS = frozenset({
    "user_id", "name", "phone_number", "kakao_subject", "account_id", "account_number",
    "card_number", "amount", "birth_year", "gender", "marital_status", "is_employed",
})


def amount_band(amount: int) -> str:
    if amount < 10_000:
        return "under_10k"
    if amount < 100_000:
        return "under_100k"
    if amount < 1_000_000:
        return "under_1m"
    return "over_1m"


def _check_keys(value) -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            if key in FORBIDDEN_KEYS:
                raise ValueError(f"event must not contain {key}")
            _check_keys(inner)
    elif isinstance(value, list):
        for inner in value:
            _check_keys(inner)


def build_event(event_type: str, outcome: str, reason: str, *, source: str, request_id: str | None,
                duration_ms: int | None, properties: dict) -> dict:
    _check_keys(properties)
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "occurred_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "source": source,
        "outcome": outcome,
        "reason": reason,
        "duration_ms": duration_ms,
        "request_id": request_id,
        "properties": properties,
    }


@dataclass(frozen=True)
class EventSink:
    """커밋된 이벤트를 쓰는 곳. events_bronze는 events.log(한 줄에 JSON 1개)와 MongoDB에, 나머지는 MongoDB에만 쓴다."""

    mongo_db: Database
    log_path: Path
    instance: str = "api"  # 어느 FastAPI 서버에서 난 이벤트인지 (api-1, api-2)
    application_log: ApplicationLog | None = None

    def warn(self, message: str, exc: Exception) -> None:
        if self.application_log is not None:
            self.application_log.write("WARNING", message, exception_type=type(exc).__name__)
        else:
            logger.warning("%s: %s", message, type(exc).__name__)

    def publish(self, items: list[tuple[str, dict]]) -> None:
        """실패해도 예외를 올리지 않는다. 돈 처리는 이미 커밋되었으므로 여기서 오류가 나면 성공한 거래가 500이 된다.
        그래서 어떤 오류든 경고만 남기고 넘어간다."""
        items = [(collection, {**event, "instance": self.instance}) for collection, event in items]
        try:
            lines = [json.dumps(event, ensure_ascii=False) for collection, event in items if collection == LOG_COLLECTION]
            if lines:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
        except Exception as exc:  # noqa: BLE001
            self.warn("event_log_write_failed", exc)
        for collection, event in items:
            try:
                self.mongo_db[collection].insert_one(dict(event))
            except PyMongoError as exc:
                # MongoDB가 죽어 있으면 남은 이벤트도 같은 시간만큼 기다리게 되므로 여기서 멈춘다.
                self.warn("mongodb_write_failed", exc)
                return
            except Exception as exc:  # noqa: BLE001
                self.warn("mongodb_write_failed", exc)


def make_sink(settings, application_log: ApplicationLog | None = None) -> EventSink:
    """설정으로 sink를 만든다. MongoDB가 죽어 있어도 시작은 되게 인덱스 생성 실패는 넘어간다."""
    from app.db.mongodb import ensure_indexes, make_mongo

    mongo_db = make_mongo(settings.mongodb_url, settings.mongodb_db)
    application_log = application_log or ApplicationLog(settings.app_log_path, settings.instance_name)
    sink = EventSink(mongo_db, Path(settings.event_log_path), settings.instance_name, application_log)
    try:
        ensure_indexes(mongo_db)
    except PyMongoError as exc:
        sink.warn("mongodb_index_setup_skipped", exc)
    return sink


@contextmanager
def transaction(engine: Engine, sink: EventSink) -> Iterator[Connection]:
    """engine.begin()과 같지만, 안에서 record()한 이벤트를 커밋이 성공한 뒤에만 sink에 쓴다. 롤백되면 버린다."""
    items: list[tuple[str, dict]] = []
    with engine.begin() as conn:
        conn.info[_PENDING] = items
        try:
            yield conn
        finally:
            conn.info.pop(_PENDING, None)
    sink.publish(items)


def record(conn: Connection, request, event_type: str, outcome: str, reason: str,
           properties: dict | None = None, source: str = "api", collection: str = "events_bronze") -> dict:
    """이벤트를 만들어 이 트랜잭션에 모아 둔다. 커밋 후 transaction()이 쓴다. request가 없으면(배치) request_id·처리 시간은 비운다."""
    from app.observability.request_id import elapsed_ms, get_request_id

    if _PENDING not in conn.info:
        raise RuntimeError("record() must be called inside events.service.transaction()")
    event = build_event(
        event_type, outcome, reason, source=source,
        request_id=get_request_id(request) if request is not None else None,
        duration_ms=elapsed_ms(request) if request is not None else None,
        properties=properties or {},
    )
    _check_keys(event)
    conn.info[_PENDING].append((collection, event))
    return event
