import json
import logging
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from fastapi import FastAPI

from app.core.time import kst_iso
from app.observability.request_id import get_request_id

logger = logging.getLogger("app.application")


def exception_details(error: Exception) -> dict:
    # 예외 원문, SQL 인자, 지역 변수, 소스 줄은 기록하지 않는다.
    return {
        "exception_type": type(error).__name__,
        "stack": [
            {"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
            for frame in traceback.extract_tb(error.__traceback__)
        ],
    }


@dataclass
class ApplicationLog:
    path: Path
    instance: str

    def __post_init__(self):
        self.path = Path(self.path)
        self._lock = Lock()

    def write(self, level: str, message: str, **fields) -> None:
        entry = {
            "timestamp": kst_iso(),
            "level": level, "message": message, "instance": self.instance, **fields,
        }
        try:
            line = json.dumps(entry, ensure_ascii=False) + "\n"
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as stream:
                    stream.write(line)
        except Exception as exc:  # noqa: BLE001
            # 로그 저장 실패가 요청 결과를 바꾸지 않게 하고 비밀값도 출력하지 않는다.
            logger.warning("application log write failed: %s", type(exc).__name__)


class ApplicationLogMiddleware:
    def __init__(self, app, sink: ApplicationLog):
        self.app = app
        self.sink = sink

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = time.perf_counter()
        status = 500
        error = None

        async def capture_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture_send)
        except Exception as exc:
            error = exc
            raise
        finally:
            from starlette.requests import Request

            request = Request(scope)
            route = scope.get("route")
            fields = {
                "method": scope["method"],
                # 원본 URL, 경로 인자, 쿼리, 본문, 헤더는 저장하지 않는다.
                "route": getattr(route, "path", "unmatched"),
                "status_code": status,
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "request_id": get_request_id(request),
                "error_code": "internal_error" if error else getattr(request.state, "error_code", None),
            }
            if error:
                fields.update(exception_details(error))
            else:
                fields.update(getattr(request.state, "exception_details", {}))
            level = "ERROR" if status >= 500 or error else "WARNING" if status >= 400 else "INFO"
            self.sink.write(level, "request_completed", **fields)


def install_application_log(app: FastAPI, sink: ApplicationLog) -> None:
    app.state.application_log = sink
    app.add_middleware(ApplicationLogMiddleware, sink=sink)
