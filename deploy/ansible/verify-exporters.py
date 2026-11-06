"""Read-only exporter and Prometheus checks; issue only HTTP GET requests."""
import argparse
import json
import subprocess
import time
import urllib.parse
import urllib.request


def get_json(url):
    with urllib.request.urlopen(url, timeout=15) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', required=True)
    args = parser.parse_args()
    result = subprocess.run(['ansible-inventory', '-i', args.inventory, '--list'],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError('Unable to read private inventory')
    inventory = json.loads(result.stdout)
    variables = inventory['_meta']['hostvars']
    host = inventory['prometheus']['hosts'][0]
    base = 'http://' + variables[host]['ansible_host'] + ':9090'
    for host in inventory['api']['hosts']:
        api = 'http://' + variables[host]['ansible_host'] + ':8000'
        for endpoint in ['/docs', '/metrics']:
            with urllib.request.urlopen(api + endpoint, timeout=15) as response:
                assert response.status == 200, host + endpoint
    expected = {'node': len(variables), 'prometheus': 1, 'loki': 1, 'grafana': 1,
                'nginx': 1, 'haproxy': 1, 'fastapi': 2, 'mariadb': 2, 'mongodb': 1}
    for _ in range(60):
        targets = get_json(base + '/api/v1/targets')['data']['activeTargets']
        counts = {job: sum(t['labels'].get('job') == job and t['health'] == 'up' for t in targets)
                  for job in expected}
        if counts == expected and len(targets) == sum(expected.values()):
            break
        time.sleep(2)
    else:
        raise RuntimeError('Exporter targets not all healthy: ' + json.dumps(counts))
    print('PASS: all Prometheus targets UP: ' + json.dumps(counts), flush=True)
    checks = {
        'nginx exporter reaches stub_status': ('nginx_up{job="nginx"}', 1),
        'HAProxy sees both API backends UP': ('haproxy_server_status{job="haproxy",proxy="fastapi",state="UP"}', 2),
        'both MariaDB exporters authenticate': ('mysql_up{job="mariadb"}', 2),
        'MongoDB exporter authenticates': ('mongodb_up{job="mongodb"}', 1),
        'replica IO thread runs': ('mysql_slave_status_slave_io_running{job="mariadb",role="replica"}', 1),
        'replica SQL thread runs': ('mysql_slave_status_slave_sql_running{job="mariadb",role="replica"}', 1),
    }
    for label, (query, count) in checks.items():
        url = base + '/api/v1/query?' + urllib.parse.urlencode({'query': query})
        values = get_json(url)['data']['result']
        assert len(values) == count and all(float(v['value'][1]) == 1 for v in values), label
        print('PASS: ' + label, flush=True)
    query = 'count by(instance)(podobank_http_requests_total{job="fastapi"})'
    for _ in range(30):
        values = get_json(base + '/api/v1/query?' + urllib.parse.urlencode({'query': query}))['data']['result']
        if len(values) == 2:
            break
        time.sleep(2)
    else:
        raise RuntimeError('FastAPI HTTP counters missing')
    print('PASS: both FastAPI HTTP counters collected; no financial writes', flush=True)


if __name__ == '__main__':
    main()
