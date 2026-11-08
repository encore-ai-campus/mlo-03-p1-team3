"""Verify real requests -> nginx/HAProxy/API -> Alloy -> Loki, without financial writes.

Run on the Ansible controller after alloy.yml:
python3 deploy/ansible/verify-proxy-logs.py --inventory inventory.json
The default checks send successful health requests. Failure probes require an explicit flag.
"""
import argparse
import json
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request


def get_json(url):
    with urllib.request.urlopen(url, timeout=15) as response:
        return json.load(response)


def wait_for_line(loki, labels, text, start, label):
    query = '{' + ','.join(key + '=' + json.dumps(value) for key, value in labels.items()) + '} |= ' + json.dumps(text)
    for _ in range(45):
        args = urllib.parse.urlencode({'query': query, 'start': str(start), 'limit': 100})
        data = get_json(loki + '/loki/api/v1/query_range?' + args)
        if any(text in line for stream in data['data']['result'] for _, line in stream['values']):
            print('PASS: ' + label, flush=True)
            return
        time.sleep(2)
    raise RuntimeError('Log not found: ' + label)


def request(url, data=None):
    req = urllib.request.Request(url, data=data, headers={
        'Content-Type': 'application/json' if data else 'text/plain',
        'Connection': 'close',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            response.read()
            return response.status, response.headers
    except urllib.error.HTTPError as error:
        error.read()
        return error.code, error.headers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', required=True)
    parser.add_argument('--read-only', action='store_true', default=True, help='Check successful health request logs only (default)')
    parser.add_argument('--include-failure-probes', action='store_false', dest='read_only', help='Explicitly generate invalid logins and one 413 for diagnostics')
    parser.add_argument('--loki-url', help='Override Loki base URL (no credentials)')
    args = parser.parse_args()
    # Capture private inventory in memory only; never print it.
    result = subprocess.run(['ansible-inventory', '-i', args.inventory, '--list'],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError('Unable to load Ansible inventory')
    inventory = json.loads(result.stdout)
    hosts = inventory['_meta']['hostvars']
    nginx = inventory['nginx']['hosts'][0]
    haproxy = inventory['haproxy']['hosts'][0]
    api = inventory['api']['hosts']
    assert len(api) == 2, 'Expected exactly two API hosts'
    base = hosts[nginx].get('app_base_url') or ('https://' + hosts[nginx].get('nginx_server_name', 'www.podobank.kro.kr'))
    loki = args.loki_url or ('http://' + hosts[inventory['loki']['hosts'][0]]['ansible_host'] + ':3100')
    if args.read_only:
        start = time.time_ns()
        marker = 'health-probe-' + secrets.token_hex(8)
        instances = {hosts[name].get('api_instance', name) for name in api}
        health = {}
        for _ in range(12):
            status, headers = request(base + '/api/v1/health?probe=' + marker)
            assert status == 200, 'Health request failed'
            backend, rid = headers.get('X-Backend-Server'), headers.get('X-Request-ID')
            assert backend in instances and rid, 'Missing backend/request identity'
            health[backend] = rid
            if set(health) == instances:
                break
        assert set(health) == instances, 'Both API hosts were not reached'
        wait_for_line(loki, {'service': 'nginx', 'log_type': 'access'}, marker, start, 'nginx access -> Alloy -> Loki')
        wait_for_line(loki, {'service': 'haproxy'}, marker, start, 'HAProxy request -> Alloy -> Loki')
        for backend, rid in sorted(health.items()):
            wait_for_line(loki, {'log_type': 'application', 'instance': backend}, rid, start, backend + ' application -> Alloy -> Loki')
        print('PASS: both API hosts and proxy requests collected without intentional errors', flush=True)
        return

    parsed = urllib.parse.urlsplit(loki)
    assert parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password
    loki = loki.rstrip('/')
    start = time.time_ns() - 5_000_000_000
    marker = 'alloy-probe-' + secrets.token_hex(8)
    instances = {hosts[name].get('api_instance', name) for name in api}
    health = {}
    for _ in range(12):
        status, headers = request(base + '/api/v1/health?alloy_probe=' + marker)
        assert status == 200, 'Health request failed'
        backend, rid = headers.get('X-Backend-Server'), headers.get('X-Request-ID')
        assert backend in instances and rid, 'Missing backend/request identity'
        health[backend] = rid
        if set(health) == instances:
            break
    assert set(health) == instances, 'Both API hosts were not reached'
    print('PASS: nginx -> HAProxy -> both FastAPI instances return HTTP 200', flush=True)

    # Unknown users generate real auth failure events through FastAPI, never direct log inserts.
    events = {}
    for _ in range(12):
        body = json.dumps({'phone_number': '019' + ''.join(str(secrets.randbelow(10)) for _ in range(8)),
                           'password': secrets.token_urlsafe(24)}).encode()
        status, headers = request(base + '/api/v1/auth/login?alloy_probe=' + marker, data=body)
        assert status == 401, 'Expected invalid-login HTTP 401'
        events[headers.get('X-Backend-Server')] = headers.get('X-Request-ID')
        if set(events) == instances:
            break
    assert set(events) == instances and all(events.values()), 'Both API event paths were not reached'

    # Nginx rejects this at its existing 1 MiB limit, before the request reaches the API.
    status, _ = request(base + '/api/v1/health?alloy_probe=' + marker + '-oversize', data=b'x' * (1024 * 1024 + 1))
    assert status == 413, 'Expected nginx client_max_body_size rejection'
    wait_for_line(loki, {'service': 'nginx', 'instance': nginx, 'log_type': 'access'}, marker, start, 'nginx access file -> Alloy -> Loki')
    wait_for_line(loki, {'service': 'nginx', 'instance': nginx, 'log_type': 'error'}, marker + '-oversize', start, 'nginx error file -> Alloy -> Loki')
    wait_for_line(loki, {'service': 'haproxy', 'instance': haproxy, 'log_type': 'service'}, marker, start, 'HAProxy HTTP journal -> Alloy -> Loki')
    for instance in sorted(instances):
        wait_for_line(loki, {'instance': instance, 'log_type': 'application'}, health[instance], start, instance + ' application file -> Alloy -> Loki')
        wait_for_line(loki, {'instance': instance, 'log_type': 'event'}, events[instance], start, instance + ' event file -> Alloy -> Loki')
        # Uvicorn runs with --no-access-log: the request line duplicated nginx access.log and app.log
        # (checked above by request ID). The API journal now holds only startup, warnings and errors.
    print('PASS: all four hosts deliver real request logs to Loki; no financial API writes.', flush=True)
    print('Probe marker: ' + marker, flush=True)


if __name__ == '__main__':
    main()
