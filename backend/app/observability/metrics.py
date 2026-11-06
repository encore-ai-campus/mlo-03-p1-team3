"""Prometheus HTTP metrics with bounded route labels and an app-local registry."""
import time

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest


class HttpMetricsMiddleware:
    def __init__(self, app, requests, duration):
        self.app, self.requests, self.duration = app, requests, duration

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path') == '/metrics':
            return await self.app(scope, receive, send)
        started, status = time.perf_counter(), 500

        async def capture(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            route = getattr(scope.get('route'), 'path', None) or 'unmatched'
            method = scope.get('method', 'OTHER')
            if method not in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD'}:
                method = 'OTHER'
            self.requests.labels(method, route, str(status)).inc()
            self.duration.labels(method, route).observe(time.perf_counter() - started)


def install_metrics(app: FastAPI):
    registry = CollectorRegistry()
    requests = Counter('podobank_http_requests_total', 'Completed HTTP requests',
                       ['method', 'route', 'status_code'], registry=registry)
    duration = Histogram('podobank_http_request_duration_seconds', 'HTTP request duration',
                         ['method', 'route'], registry=registry,
                         buckets=(.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10))
    app.add_middleware(HttpMetricsMiddleware, requests=requests, duration=duration)

    @app.get('/metrics', include_in_schema=False)
    def metrics():
        return Response(generate_latest(registry), headers={'Content-Type': CONTENT_TYPE_LATEST})
