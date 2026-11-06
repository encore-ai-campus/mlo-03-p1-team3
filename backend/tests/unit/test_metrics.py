from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.observability.metrics import install_metrics


def make_metrics_app():
    app = FastAPI()
    install_metrics(app)

    @app.get('/items/{item_id}')
    def item(item_id: str):
        return {'ok': True}

    @app.get('/failure')
    def failure():
        raise HTTPException(409, 'expected failure')

    @app.get('/crash')
    def crash():
        raise RuntimeError('private-data')

    return app


def test_metrics_count_status_latency_and_never_label_customer_values():
    with TestClient(make_metrics_app()) as browser:
        browser.get('/items/private-id?secret=private-query')
        browser.get('/failure')
        browser.get('/unknown-private-path')
        result = browser.get('/metrics')
        assert result.status_code == 200
        assert 'podobank_http_requests_total{method="GET",route="/items/{item_id}",status_code="200"} 1.0' in result.text
        assert 'route="/failure",status_code="409"' in result.text
        assert 'route="unmatched",status_code="404"' in result.text
        assert 'podobank_http_request_duration_seconds_bucket' in result.text
        assert 'private-' not in result.text
        assert 'route="/metrics"' not in browser.get('/metrics').text


def test_registry_is_isolated_and_unhandled_failure_is_recorded():
    with TestClient(make_metrics_app(), raise_server_exceptions=False) as browser:
        assert browser.get('/crash').status_code == 500
        assert 'route="/crash",status_code="500"' in browser.get('/metrics').text
    with TestClient(make_metrics_app()) as other:
        assert 'route="/crash"' not in other.get('/metrics').text
