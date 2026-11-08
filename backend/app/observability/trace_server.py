"""Temporary transport diagnostics for the pinned Uvicorn 0.54.0 httptools protocol."""
import time

import uvicorn
from uvicorn.protocols.http.httptools_impl import HttpToolsProtocol


class TimingProtocol(HttpToolsProtocol):
    def connection_made(self, transport):
        self._connection_ns = time.time_ns()
        super().connection_made(transport)

    def data_received(self, data):
        self._read_ns = time.time_ns()
        super().data_received(data)

    def _start_asgi_task(self, cycle, app):
        timings = {
            "transport.connection_ns": self._connection_ns,
            "transport.read_ns": self._read_ns,
            "transport.headers_ns": time.time_ns(),
        }

        async def observed(scope, receive, send):
            timings["transport.asgi_ns"] = time.time_ns()
            scope.setdefault("state", {})["transport_timing"] = timings
            return await app(scope, receive, send)

        super()._start_asgi_task(cycle, observed)


if __name__ == "__main__":
    uvicorn.run("app.main:create_app", factory=True, host="0.0.0.0", port=8000,
                http=TimingProtocol)
