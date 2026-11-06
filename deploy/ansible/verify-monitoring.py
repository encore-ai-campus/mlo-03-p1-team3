"""Run on the controller after monitoring.yml; only HTTP API calls and read-only queries.
Two invalid-login requests intentionally produce real FastAPI failure events.
"""
import base64
import json
from pathlib import Path
import secrets
import shlex
import time
import urllib.error
import urllib.parse
import urllib.request

PROM = 'http://192.168.0.198:9090'
LOKI = 'http://192.168.0.199:3100'
GRAFANA = 'http://192.168.0.200:3000'


def get_json(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=15) as r:
        return json.load(r)


def wait_for(check, label, attempts=45):
    for _ in range(attempts):
        try:
            value = check()
            if value:
                print(label + ': PASS', flush=True)
                return value
        except (urllib.error.URLError, KeyError, ValueError):
            pass
        time.sleep(2)
    raise RuntimeError(label + ' did not become ready')


def targets_ready():
    targets = get_json(PROM + '/api/v1/targets')['data']['activeTargets']
    return targets if len(targets) == 20 and all(t['health'] == 'up' for t in targets) else None


targets = wait_for(targets_ready, 'Prometheus 20 targets (10 nodes + 10 service endpoints)')
print('Prometheus targets:', len(targets), flush=True)
private = Path(__file__).resolve().parents[1] / 'vm' / 'monitoring.env'
values = {}
for line in private.read_text().splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        key, raw = line.split('=', 1)
        parts = shlex.split(raw)
        values[key.strip()] = parts[0] if parts else ''
auth = base64.b64encode(('admin:' + values['GRAFANA_ADMIN_PASSWORD']).encode()).decode()
headers = {'Authorization': 'Basic ' + auth}
sources = get_json(GRAFANA + '/api/datasources', headers)
assert {s['uid'] for s in sources} >= {'podobank-prometheus', 'podobank-loki'}
for uid in ('podobank-prometheus', 'podobank-loki'):
    def source_ready(uid=uid):
        result = get_json(GRAFANA + '/api/datasources/uid/' + uid + '/health', headers)
        return result if result.get('status', '').lower() == 'ok' else None
    wait_for(source_ready, 'Grafana data source ' + uid)

requests = []
for _ in range(12):
    body = {'phone_number': '019' + ''.join(str(secrets.randbelow(10)) for _ in range(8)), 'password': secrets.token_urlsafe(24)}
    req = urllib.request.Request('https://www.podobank.kro.kr/api/v1/auth/login', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req, timeout=15)
        raise RuntimeError('Expected a failed login for a nonexistent user')
    except urllib.error.HTTPError as error:
        assert error.code == 401, error.code
        requests.append((error.headers['X-Request-ID'], error.headers.get('X-Backend-Server')))
    if {backend for _, backend in requests} == {'api-1', 'api-2'}:
        break
assert {backend for _, backend in requests} == {'api-1', 'api-2'}, requests
for rid, backend in requests:
    def find_event():
        query = '{log_type="event",instance="' + backend + '"} |= "' + rid + '"'
        args = urllib.parse.urlencode({'query': query, 'start': str(time.time_ns() - 300_000_000_000), 'limit': 20})
        results = get_json(LOKI + '/loki/api/v1/query_range?' + args)['data']['result']
        return results if any(rid in line for stream in results for _, line in stream['values']) else None
    wait_for(find_event, 'FastAPI -> event file -> Alloy -> Loki ' + backend)
    print('Verified request_id:', rid, flush=True)
for backend in ('api-1', 'api-2'):
    def find_journal():
        query = '{log_type="service",instance="' + backend + '"} |= "/api/v1/auth/login"'
        args = urllib.parse.urlencode({'query': query, 'start': str(time.time_ns() - 300_000_000_000), 'limit': 20})
        return get_json(LOKI + '/loki/api/v1/query_range?' + args)['data']['result']
    wait_for(find_journal, 'API service journal -> Alloy -> Loki ' + backend)
print('PASS: metrics, Grafana data sources, event and service log pipelines.', flush=True)
