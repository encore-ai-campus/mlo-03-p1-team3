import asyncio
import socket

import httpx
import uvicorn
from fastapi import FastAPI, Request

from app.observability.trace_server import TimingProtocol


def test_protocol_records_transport_stages_without_changing_response():
    async def scenario():
        app = FastAPI()

        @app.get("/probe")
        async def probe(request: Request):
            return request.scope["state"]["transport_timing"]

        server = uvicorn.Server(uvicorn.Config(
            app, http=TimingProtocol, lifespan="off", log_level="critical", access_log=False,
        ))
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        task = asyncio.create_task(server.serve(sockets=[sock]))
        try:
            for _ in range(100):
                if server.started:
                    break
                await asyncio.sleep(0.01)
            async with httpx.AsyncClient(trust_env=False) as client:
                response = await client.get(f"http://127.0.0.1:{sock.getsockname()[1]}/probe")
            assert response.status_code == 200
            values = response.json()
            assert (values["transport.connection_ns"] <= values["transport.read_ns"]
                    <= values["transport.headers_ns"] <= values["transport.asgi_ns"])
        finally:
            server.should_exit = True
            await task
            sock.close()

    asyncio.run(scenario())
