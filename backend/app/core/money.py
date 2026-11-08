"""돈이 움직이는 요청을 한 트랜잭션으로 처리한다.

성공하면 커밋하고 결과를 돌려준다(이벤트는 커밋 뒤에 쓴다). 업무 오류(AppError)면 롤백한 뒤 실패 이벤트를 따로 남기고 오류를 그대로 올린다.
"""

from collections.abc import Callable

from fastapi import Request
from sqlalchemy.engine import Connection

from app.api.events.service import record, transaction
from app.core.errors import AppError
from app.db.mariadb import translate_db_errors, with_deadlock_retry
from app.observability.tracing import traced


@traced("money.execute")
def run_money(request: Request, event_type: str, properties: dict,
              action: Callable[[Connection], dict]) -> dict:
    engine, sink = request.app.state.engine, request.app.state.events

    def once() -> dict:
        with transaction(engine, sink) as conn:
            return action(conn)

    with translate_db_errors():
        try:
            return with_deadlock_retry(once)
        except AppError as exc:
            with transaction(engine, sink) as conn:
                record(conn, request, event_type, "failure", exc.code, properties)
            raise
