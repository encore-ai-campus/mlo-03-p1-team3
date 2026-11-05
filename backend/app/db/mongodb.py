from pymongo import MongoClient
from pymongo.database import Database


def make_mongo(url: str, db_name: str) -> Database:
    # 이벤트는 돈 처리 응답 직전에 쓴다. MongoDB가 죽거나 멈춰도 요청이 오래 붙잡히지 않게 기다리는 시간을 짧게 둔다.
    client = MongoClient(url, serverSelectionTimeoutMS=500, connectTimeoutMS=500, socketTimeoutMS=2000)
    return client[db_name]


EVENT_COLLECTIONS = ("events_bronze", "card_payment_locations")


def ensure_indexes(db: Database) -> None:
    """같은 이벤트가 두 번 들어와도 하나만 남도록 event_id를 고유값으로 둔다."""
    for name in EVENT_COLLECTIONS:
        db[name].create_index("event_id", unique=True)
