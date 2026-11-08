"""Opt-in OTLP tracing; SQL text is retained, credentials and arguments are not."""
import asyncio
import os
import time
from contextlib import asynccontextmanager, contextmanager, suppress
from functools import wraps

import anyio.to_thread
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Status, StatusCode
from sqlalchemy import event

from app.observability.pool_observer import PoolObserver

_provider = None
_noop = trace.NoOpTracerProvider()
_original_run_sync = anyio.to_thread.run_sync
_ATTRIBUTES = frozenset({
    "http.method", "http.request.method", "http.route", "http.status_code",
    "http.response.status_code", "db.system", "db.system.name", "db.name",
    "db.namespace", "db.statement", "db.query.text", "db.operation",
    "db.operation.name", "error.type", "exception.type", "exception.escaped",
    "runtime.lag_seconds", "threadpool.borrowed", "threadpool.total",
    "transport.connection_ns", "transport.read_ns", "transport.headers_ns", "transport.asgi_ns",
})


class SafeExporter(SpanExporter):
    """Prevent exception messages/SQL arguments and HTTP credentials leaving the app."""

    def __init__(self, exporter):
        self.exporter = exporter

    def export(self, spans):
        cleaned = []
        for item in spans:
            cleaned.append(ReadableSpan(
                name=item.name, context=item.context, parent=item.parent,
                resource=item.resource, kind=item.kind,
                attributes={k: v for k, v in item.attributes.items() if k in _ATTRIBUTES},
                events=[Event(e.name, {k: v for k, v in e.attributes.items() if k in _ATTRIBUTES},
                              e.timestamp) for e in item.events],
                status=Status(item.status.status_code), start_time=item.start_time,
                end_time=item.end_time, instrumentation_scope=item.instrumentation_scope,
            ))
        return self.exporter.export(cleaned)

    def shutdown(self):
        self.exporter.shutdown()

    def force_flush(self, timeout_millis=30000):
        return self.exporter.force_flush(timeout_millis)


_tracer_cache = (None, None)


def _tracer():
    """Reuse one tracer per provider; get_tracer() runs warning checks on every call."""
    global _tracer_cache
    provider = _provider or _noop
    if _tracer_cache[0] is not provider:
        _tracer_cache = (provider, provider.get_tracer("podobank"))
    return _tracer_cache[1]


def _unsampled_parent():
    # ParentBased sampling drops every child of an unsampled parent, so skip building them.
    context = trace.get_current_span().get_span_context()
    return context.is_valid and not context.trace_flags.sampled


@contextmanager
def span(name):
    if _unsampled_parent():
        yield trace.INVALID_SPAN
        return
    tracer = _tracer()
    with tracer.start_as_current_span(name, record_exception=False,
                                     set_status_on_exception=False) as current:
        try:
            yield current
        except Exception as exc:
            current.set_attribute("error.type", type(exc).__name__)
            current.set_status(StatusCode.ERROR)
            raise


def traced(name):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with span(name):
                return function(*args, **kwargs)
        return wrapped
    return decorate


def trace_id():
    context = trace.get_current_span().get_span_context()
    return format(context.trace_id, "032x") if context.is_valid else None


def instrument_acquisition(engine):
    original = engine.connect

    @wraps(original)
    def connect(*args, **kwargs):
        with span("db.acquire"):
            return original(*args, **kwargs)

    engine.connect = connect


def instrument_queries(engine):
    # Public execution events support the application's SQLAlchemy 2.1 engine.
    def before(conn, cursor, statement, parameters, context, executemany):
        if _unsampled_parent():
            context._podobank_span = None
            return
        context._podobank_span = _tracer().start_span(
            "db.query", kind=trace.SpanKind.CLIENT,
            attributes={"db.system": "mysql", "db.statement": statement},
        )

    def after(conn, cursor, statement, parameters, context, executemany):
        if current := getattr(context, "_podobank_span", None):
            current.end()
            context._podobank_span = None

    def failed(exception_context):
        context = exception_context.execution_context
        if current := getattr(context, "_podobank_span", None):
            current.set_attribute("error.type", type(exception_context.original_exception).__name__)
            current.set_status(StatusCode.ERROR)
            current.end()
            context._podobank_span = None

    event.listen(engine, "before_cursor_execute", before)
    event.listen(engine, "after_cursor_execute", after)
    event.listen(engine, "handle_error", failed)


async def _traced_run_sync(func, *args, **kwargs):
    if not trace.get_current_span().is_recording():
        return await _original_run_sync(func, *args, **kwargs)
    # Starts on the event loop and ends when the worker begins executing.
    queued = _tracer().start_span("threadpool.wait")

    def run(*values):
        queued.end()
        return func(*values)

    try:
        return await _original_run_sync(run, *args, **kwargs)
    finally:
        if queued.is_recording():
            queued.end()


def instrument_http(app, provider):
    def transport_hook(current, scope):
        for key, value in scope.get("state", {}).get("transport_timing", {}).items():
            if key in _ATTRIBUTES and isinstance(value, int):
                current.set_attribute(key, value)

    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=provider, excluded_urls=r"/metrics$",
        server_request_hook=transport_hook,
        http_capture_headers_server_request=[], http_capture_headers_server_response=[],
        exclude_spans=["receive", "send"],
    )


def install_tracing(app, settings):
    global _provider
    if not settings.otel_traces_endpoint:
        return
    _provider = TracerProvider(
        resource=Resource({"service.name": "podobank-api", "service.instance.id": settings.instance_name}),
        sampler=ParentBased(TraceIdRatioBased(settings.otel_sample_ratio)),
    )
    _provider.add_span_processor(BatchSpanProcessor(
        SafeExporter(OTLPSpanExporter(endpoint=settings.otel_traces_endpoint, timeout=1)),
        max_queue_size=8192, max_export_batch_size=512, schedule_delay_millis=1000,
    ))
    app.state.tracing_provider = _provider
    instrument_http(app, _provider)
    instrument_queries(app.state.engine)
    instrument_acquisition(app.state.engine)
    if os.environ.get("POOL_OBSERVE_ENABLED", "false").lower() == "true":
        app.state.pool_observer = PoolObserver(app.state.engine)
    anyio.to_thread.run_sync = _traced_run_sync


async def _monitor(app):
    limiter = anyio.to_thread.current_default_thread_limiter()
    next_pool_snapshot = 0
    while True:
        expected = asyncio.get_running_loop().time() + 0.1
        await asyncio.sleep(0.1)
        lag = max(0.0, asyncio.get_running_loop().time() - expected)
        app.state.loop_lag.set(lag)
        app.state.threadpool_borrowed.set(limiter.borrowed_tokens)
        app.state.threadpool_total.set(limiter.total_tokens)
        if hasattr(app.state, "pool_observer") and time.monotonic() >= next_pool_snapshot:
            app.state.application_log.write("INFO", "pool_snapshot", pid=os.getpid(),
                                            **app.state.pool_observer.snapshot())
            next_pool_snapshot = time.monotonic() + 1
        if lag > 0.1:
            end = time.time_ns()
            current = _tracer().start_span(
                "runtime.event_loop_lag", start_time=end - int(lag * 1e9),
                attributes={"runtime.lag_seconds": lag, "threadpool.borrowed": limiter.borrowed_tokens,
                            "threadpool.total": limiter.total_tokens},
            )
            current.end(end_time=end)


@asynccontextmanager
async def tracing_lifespan(app):
    provider = getattr(app.state, "tracing_provider", None)
    task = asyncio.create_task(_monitor(app)) if provider else None
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            await asyncio.to_thread(provider.shutdown)
