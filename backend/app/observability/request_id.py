import time
import uuid

from fastapi import FastAPI, Request
from starlette.datastructures import MutableHeaders

from app.observability.tracing import trace_id


def get_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if request_id is None:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
    return request_id


def elapsed_ms(request: Request) -> int | None:
    started = getattr(request.state, "started_at", None)
    return None if started is None else int((time.perf_counter() - started) * 1000)


class RequestIdMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope)
        request.state.started_at = time.perf_counter()
        request_id = get_request_id(request)

        async def capture_send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                if current_trace := trace_id():
                    headers["X-Trace-ID"] = current_trace
            await send(message)

        await self.app(scope, receive, capture_send)


def install_request_id(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)
