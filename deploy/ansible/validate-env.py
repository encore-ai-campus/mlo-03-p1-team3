"""Check public deployment settings without displaying private environment values."""
import ipaddress
import json
import shlex
import sys
from pathlib import Path

values = {}
for line in Path(sys.argv[1]).read_text().splitlines():
    line = line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    key, value = line.split('=', 1)
    parts = shlex.split(value, comments=True)
    values[key.strip()] = parts[0] if parts else ''

expected = json.loads(sys.argv[2])
for key, value in expected.items():
    if values.get(key) != value:
        raise SystemExit(f'Deployment setting does not match inventory: {key}')
for key in ('MARIADB_PASSWORD', 'MARIADB_REPL_PASSWORD', 'MONGODB_ADMIN_PASSWORD'):
    if not values.get(key) or values[key].startswith('change-me'):
        raise SystemExit(f'Configure a real private value for {key}')
cidr = ipaddress.ip_network(values['MONGODB_CLIENT_CIDR'], strict=True)
if cidr.version != 4 or cidr.prefixlen != 24 or not cidr.is_private:
    raise SystemExit('Configure a private IPv4 /24 for MONGODB_CLIENT_CIDR')
subnet = str(cidr.network_address).rsplit('.', 1)[0] + '.%'
if values.get('MARIADB_CLIENT_SUBNET') != subnet:
    raise SystemExit('MariaDB and MongoDB client networks must match')
for key in ('NGINX_IP', 'HAPROXY_IP', 'API1_IP', 'API2_IP', 'MARIADB_MASTER_IP', 'MARIADB_REPLICA_IP', 'MONGODB_IP'):
    if ipaddress.ip_address(values[key]) not in cidr:
        raise SystemExit('VM address outside configured LAN: ' + key)
print('Deployment IPs and client subnet match inventory.')
