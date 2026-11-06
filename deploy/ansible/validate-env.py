"""Check public deployment settings without displaying private environment values."""
import json
from pathlib import Path
import shlex
import sys

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
if values.get('MARIADB_CLIENT_SUBNET') != '192.168.0.%':
    raise SystemExit('Configure MARIADB_CLIENT_SUBNET=192.168.0.% for Workbench access')
if values.get('MONGODB_CLIENT_CIDR') != '192.168.0.0/24':
    raise SystemExit('Configure MONGODB_CLIENT_CIDR=192.168.0.0/24 for LAN access')
print('Deployment IPs match inventory.')
