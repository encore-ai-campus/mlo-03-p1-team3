#!/usr/bin/env bash
# Run from WSL. Existing VM disks and monitoring data are preserved on reapply.
# bash deploy/monitoring.sh [--verify]
set -euo pipefail
cd "$(dirname "$0")/.."
export ANSIBLE_PIPELINING=true ANSIBLE_TIMEOUT=60
inventory="${ANSIBLE_INVENTORY:-inventory.json}"
python3 - "$inventory" <<'PY'
import json,shlex,subprocess,sys
from pathlib import Path
inventory=json.loads(subprocess.check_output(['ansible-inventory','-i',sys.argv[1],'--list'],text=True))
for group,ip in [('prometheus','192.168.0.198'),('loki','192.168.0.199'),('grafana','192.168.0.200')]:
 hosts=inventory.get(group,{}).get('hosts',[])
 if len(hosts)!=1 or inventory['_meta']['hostvars'][hosts[0]]['ansible_host']!=ip:
  raise SystemExit('Configure the expected monitoring host in inventory: '+group)
for file,required in [('deploy/vm/vm.env',['LOKI_PUSH_URL']),('deploy/vm/monitoring.env',['GRAFANA_ADMIN_PASSWORD'])]:
 values={}
 for line in Path(file).read_text().splitlines():
  if '=' in line and not line.lstrip().startswith('#'):
   k,v=line.split('=',1);p=shlex.split(v,comments=True);values[k.strip()]=p[0] if p else ''
 for key in required:
  if not values.get(key) or values[key].startswith('change-me'):
   raise SystemExit('Configure private setting: '+key)
print('Monitoring preflight passed; private values hidden.')
PY
bash deploy/terraform/monitoring/apply.sh
ansible-playbook -i "$inventory" deploy/ansible/monitoring.yml
if [[ "${1:-}" == --verify ]]; then
  python3 deploy/ansible/verify-exporters.py --inventory "$inventory"
  python3 deploy/ansible/verify-monitoring.py
  python3 deploy/ansible/verify-proxy-logs.py --inventory "$inventory"
fi
