import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.observability import tracing


@pytest.fixture
def traces(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(tracing.SafeExporter(exporter)))
    monkeypatch.setattr(tracing, "_provider", provider)
    yield provider, exporter
    provider.shutdown()


def test_exception_does_not_export_secret_arguments(traces):
    _, exporter = traces
    with pytest.raises(RuntimeError), tracing.span("db.acquire"):
        raise RuntimeError("password=secret-password; session=secret-cookie")
    [finished] = exporter.get_finished_spans()
    assert finished.status.status_code.name == "ERROR"
    assert finished.attributes["error.type"] == "RuntimeError"
    assert "secret" not in finished.to_json()


def test_http_parent_reaches_sync_worker_and_sql_is_visible(traces):
    provider, exporter = traces
    app = FastAPI()

    @app.get("/accounts/{account_id}")
    def account(account_id: str):
        with tracing.span("db.query") as child:
            child.set_attribute("db.statement", "SELECT balance FROM accounts WHERE id = %(id)s")
        return {"ok": True}

    tracing.instrument_http(app, provider)
    with TestClient(app) as client:
        result = client.get("/accounts/123?password=secret", headers={"Cookie": "session=secret"})
    assert result.status_code == 200
    spans = exporter.get_finished_spans()
    child = next(s for s in spans if s.name == "db.query")
    parent = next(s for s in spans if s.kind.name == "SERVER")
    assert child.context.trace_id == parent.context.trace_id
    assert child.parent.span_id == parent.context.span_id
    assert "SELECT balance" in child.attributes["db.statement"]
    saved = json.dumps([json.loads(s.to_json()) for s in spans])
    assert "secret" not in saved
    assert "http.request.header.cookie" not in saved


def test_connection_acquisition_wait_is_separate_from_query(traces):
    _, exporter = traces

    class Engine:
        def connect(self):
            time.sleep(0.03)
            return "connection"

    engine = Engine()
    tracing.instrument_acquisition(engine)
    assert engine.connect() == "connection"
    [finished] = exporter.get_finished_spans()
    assert finished.name == "db.acquire"
    assert finished.end_time - finished.start_time >= 25_000_000


def test_sqlalchemy_events_trace_sql_but_not_parameters(traces):
    _, exporter = traces
    # This checks instrumentation callbacks only, not banking or DB concurrency.
    engine = create_engine("sqlite://")
    tracing.instrument_queries(engine)
    with tracing.span("request"), engine.connect() as conn:
        assert conn.execute(text("SELECT :value"), {"value": "secret-password"}).scalar() == "secret-password"
        with pytest.raises(OperationalError):
            conn.execute(text("SELECT missing_column"))
    spans = exporter.get_finished_spans()
    queries = [s for s in spans if s.name == "db.query"]
    assert len(queries) == 2
    assert queries[1].status.status_code.name == "ERROR"
    assert queries[0].attributes["db.statement"] == "SELECT ?"
    assert "secret-password" not in json.dumps([json.loads(s.to_json()) for s in spans])
    engine.dispose()


def test_threadpool_wait_is_recorded_separately(traces, monkeypatch):
    provider, exporter = traces
    monkeypatch.setattr(tracing.anyio.to_thread, "run_sync", tracing._traced_run_sync)
    app = FastAPI()

    @app.get("/work")
    def work():
        with tracing.span("work"):
            return {"ok": True}

    tracing.instrument_http(app, provider)
    with TestClient(app) as client:
        assert client.get("/work").status_code == 200
    spans = exporter.get_finished_spans()
    waiting = next(s for s in spans if s.name == "threadpool.wait")
    working = next(s for s in spans if s.name == "work")
    assert waiting.context.trace_id == working.context.trace_id
    assert waiting.end_time <= working.start_time


def _provider_with(sampler, monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider(sampler=sampler)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(tracing, "_provider", provider)
    return provider, exporter


def test_children_of_unsampled_parent_are_skipped(monkeypatch):
    from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, ParentBased

    provider, exporter = _provider_with(ParentBased(ALWAYS_OFF), monkeypatch)
    engine = create_engine("sqlite://")
    tracing.instrument_queries(engine)
    with provider.get_tracer("test").start_as_current_span("request") as parent:
        assert not parent.get_span_context().trace_flags.sampled
        with tracing.span("child") as child:
            assert child is tracing.trace.INVALID_SPAN
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    assert exporter.get_finished_spans() == ()
    provider.shutdown()


def test_children_of_sampled_parent_are_recorded(monkeypatch):
    from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased

    provider, exporter = _provider_with(ParentBased(ALWAYS_ON), monkeypatch)
    engine = create_engine("sqlite://")
    tracing.instrument_queries(engine)
    with provider.get_tracer("test").start_as_current_span("request"):
        with tracing.span("child"):
            pass
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    names = sorted(s.name for s in exporter.get_finished_spans())
    assert names == ["child", "db.query", "request"]
    provider.shutdown()


def test_root_span_without_parent_still_uses_sampler(monkeypatch):
    from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased

    provider, exporter = _provider_with(ParentBased(ALWAYS_ON), monkeypatch)
    with tracing.span("batch.job"):
        pass
    assert [s.name for s in exporter.get_finished_spans()] == ["batch.job"]
    provider.shutdown()


def test_tracer_is_created_once_per_provider(monkeypatch):
    from opentelemetry.sdk.trace.sampling import ALWAYS_ON

    provider, _ = _provider_with(ALWAYS_ON, monkeypatch)
    calls = []
    original = provider.get_tracer
    monkeypatch.setattr(provider, "get_tracer", lambda *a, **k: calls.append(a) or original(*a, **k))
    monkeypatch.setattr(tracing, "_tracer_cache", (None, None))
    for _ in range(5):
        with tracing.span("x"):
            pass
    assert len(calls) == 1
    provider.shutdown()
