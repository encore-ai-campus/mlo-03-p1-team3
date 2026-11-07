"""Run on the controller after monitoring.yml; only HTTP API calls and read-only queries.
All checks are read-only and never generate deliberate failed business events.
"""
import argparse
import base64
import json
import shlex
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--inventory', required=True)
args = parser.parse_args()
result = subprocess.run(['ansible-inventory', '-i', args.inventory, '--list'], capture_output=True, text=True, check=True)
inventory = json.loads(result.stdout)
hosts = inventory['_meta']['hostvars']
def endpoint(group, port):
    return 'http://' + hosts[inventory[group]['hosts'][0]]['ansible_host'] + ':' + str(port)
PROM, LOKI, GRAFANA = endpoint('prometheus', 9090), endpoint('loki', 3100), endpoint('grafana', 3000)


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

print('PASS: all metrics targets and both Grafana data sources; no intentional failed logins generated.', flush=True)
