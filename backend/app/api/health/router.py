from fastapi import APIRouter, Request
from pymongo.errors import PyMongoError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import AppError

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request):
    try:
        with request.app.state.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise AppError(503, "database_unavailable", "데이터베이스에 연결할 수 없습니다") from exc

    try:
        request.app.state.mongo.command("ping")
        mongodb = "ok"
    except PyMongoError:
        mongodb = "down"
    return {"mariadb": "ok", "mongodb": mongodb}
