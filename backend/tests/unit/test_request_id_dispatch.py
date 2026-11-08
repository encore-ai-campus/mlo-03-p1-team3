from contextvars import ContextVar

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.observability import request_id


def test_streamed_response_keeps_request_and_endpoint_trace_context(monkeypatch):
    app = FastAPI()
    trace = ContextVar("endpoint_trace", default=None)
    monkeypatch.setattr(request_id, "trace_id", trace.get)
    request_id.install_request_id(app)

    @app.get("/stream")
    async def endpoint(request: Request):
        trace.set("endpoint-trace")

        async def body():
            yield b"first"
            yield b"second"

        return StreamingResponse(body(), headers={"X-Endpoint": request.state.request_id})

    with TestClient(app) as client:
        response = client.get("/stream")
    assert response.content == b"firstsecond"
    assert response.headers["x-request-id"] == response.headers["x-endpoint"]
    assert response.headers["x-trace-id"] == "endpoint-trace"
