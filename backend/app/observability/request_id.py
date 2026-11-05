import time
import uuid

from fastapi import FastAPI, Request


def get_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if request_id is None:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
    return request_id


def elapsed_ms(request: Request) -> int | None:
    started = getattr(request.state, "started_at", None)
    return None if started is None else int((time.perf_counter() - started) * 1000)


def install_request_id(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.started_at = time.perf_counter()
        request_id = get_request_id(request)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
