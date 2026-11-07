"""Generate public network settings and a private inventory from one lab .env."""
import argparse
import ipaddress
import json
import shlex
import string
import subprocess
from pathlib import Path

ROLES = [
    ('nginx', 'NGINX_IP', 'nginx', 1, 1024),
    ('haproxy', 'HAPROXY_IP', 'haproxy', 1, 1024),
    ('api-1', 'API1_IP', 'api', 2, 2048),
    ('api-2', 'API2_IP', 'api', 2, 2048),
    ('mariadb-master', 'MARIADB_MASTER_IP', 'mariadb_master', 2, 2048),
    ('mariadb-replica', 'MARIADB_REPLICA_IP', 'mariadb_replica', 1, 2048),
    ('mongodb', 'MONGODB_IP', 'mongodb', 2, 2048),
    ('prometheus', 'PROMETHEUS_IP', 'prometheus', 2, 2048),
    ('loki', 'LOKI_IP', 'loki', 2, 2048),
    ('grafana', 'GRAFANA_IP', 'grafana', 1, 1024),
]


def read_env(path):
    values = {}
    for line in Path(path).read_text().splitlines():
        key, sep, value = line.strip().removeprefix('export ').partition('=')
        if sep and not key.startswith('#'):
            parts = shlex.split(value, comments=True)
            if len(parts) > 1:
                raise ValueError('Quote values containing spaces in private .env')
            values[key.strip()] = parts[0] if parts else ''
    return values


def configuration(values):
    network = ipaddress.ip_network(values['LAN_CIDR'], strict=True)
    if network.version != 4 or network.prefixlen != 24 or not network.is_private:
        raise ValueError('LAN_CIDR must be a private IPv4 /24 network')
    gateway = ipaddress.ip_address(values['LAN_GATEWAY'])
    start = int(values.get('VM_IP_START', '191'))
    if gateway not in network or gateway in (network.network_address, network.broadcast_address):
        raise ValueError('LAN_GATEWAY must be a usable address in LAN_CIDR')
    if start < 1 or start + len(ROLES) - 1 >= 255:
        raise ValueError('VM address range exceeds the LAN')
    addresses = {key: str(network.network_address + start + i) for i, (_, key, _, _, _) in enumerate(ROLES)}
    if str(gateway) in addresses.values():
        raise ValueError('VM addresses overlap the gateway')
    return network, addresses


def select_network(values, local_ips, reachable):
    candidates = [('LAN_CIDR', 'LAN_GATEWAY'), ('FALLBACK_LAN_CIDR', 'FALLBACK_LAN_GATEWAY')]
    for cidr_key, gateway_key in candidates:
        if not values.get(cidr_key) or not values.get(gateway_key):
            continue
        candidate = {**values, 'LAN_CIDR': values[cidr_key], 'LAN_GATEWAY': values[gateway_key]}
        network, _ = configuration(candidate)
        if any(ipaddress.ip_address(ip) in network for ip in local_ips) and reachable(candidate['LAN_GATEWAY']):
            return candidate
    raise ValueError('Neither preferred nor fallback network is reachable on the controller LAN')


def detect_network(values):
    result = subprocess.run(['ip', '-j', '-4', 'address', 'show'], capture_output=True, text=True, check=True)
    ips = [address['local'] for interface in json.loads(result.stdout)
           for address in interface.get('addr_info', []) if address.get('scope') == 'global']
    def reachable(ip):
        return subprocess.run(['ping', '-c', '1', '-W', '1', ip], capture_output=True, check=False).returncode == 0
    selected = select_network(values, ips, reachable)
    print('Selected reachable LAN: ' + selected['LAN_CIDR'] +
          (' (preferred)' if selected['LAN_CIDR'] == values['LAN_CIDR'] else ' (fallback)'))
    return selected


def update_env(path, changes):
    values = read_env(path)
    values.update(changes)
    path.write_text(''.join(k + '=' + shlex.quote(v) + '\n' for k, v in values.items()))
    path.chmod(0o600)


def generate(root, env_path, detect=False):
    values = read_env(env_path)
    if detect:
        values = detect_network(values)
    network, addresses = configuration(values)
    runtime = root / 'deploy/lab/.runtime'
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    prefix = values.get('VM_PREFIX', 'podobank')
    if not prefix or any(c not in string.ascii_lowercase + string.digits + '-' for c in prefix):
        raise ValueError('VM_PREFIX must contain lowercase letters, digits and hyphens')
    lab_repo = Path(values['LAB_REPO'])
    proxy = lab_repo / 'guest-proxy.sh'
    if not proxy.is_file():
        raise ValueError('LAB_REPO must contain guest-proxy.sh')
    key = values['VM_SSH_KEY']
    if not Path(key + '.pub').is_file():
        raise ValueError('VM_SSH_KEY public key missing')
    subnet = str(network.network_address).rsplit('.', 1)[0]
    vm_env = root / 'deploy/vm/vm.env'
    update_env(vm_env, {**addresses, 'MARIADB_CLIENT_SUBNET': subnet + '.%',
        'MONGODB_CLIENT_CIDR': str(network), 'LOKI_PUSH_URL': 'http://' + addresses['LOKI_IP'] + ':3100/loki/api/v1/push',
        'NGINX_TLS_ENABLED': values.get('NGINX_TLS_ENABLED', 'false'), 'RESET_DATABASES': 'false', 'REPO_REF': 'main',
        'KAKAO_REDIRECT_URI': 'http://' + addresses['NGINX_IP'] + '/auth/kakao/callback'})
    inventory = {'all': {'vars': {
        'ansible_user': values.get('VM_SSH_USER', 'ubuntu'), 'ansible_ssh_private_key_file': key,
        'ansible_python_interpreter': '/usr/bin/python3',
        'ansible_ssh_common_args': '-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=' + shlex.quote(str(runtime / 'known_hosts')) + ' -o ' + shlex.quote('ProxyCommand=bash ' + shlex.quote(str(proxy)) + ' %h %p'),
        'lan_cidr': str(network), 'mariadb_client_subnet': subnet + '.%', 'mongodb_client_cidr': str(network),
        'ssh_allowed_cidrs': [str(network)], 'reset_databases': False,
        'monitoring_enabled': True, 'frontend_enabled': True, 'frontend_build': True,
        'backend_source_dir': str(root / 'backend'), 'app_base_url': values.get('APP_BASE_URL') or 'http://' + addresses['NGINX_IP'],
    }, 'children': {}}}
    vms = {}
    for role, key_name, group, cpus, memory in ROLES:
        name = role if group == 'api' else prefix + '-' + role
        host = {'ansible_host': addresses[key_name]}
        if group == 'api':
            host.update(api_instance=role, migrate_schema='1' if role == 'api-1' else '0')
        if group in ['prometheus', 'loki', 'grafana']:
            host['monitoring_port'] = {'prometheus': 9090, 'loki': 3100, 'grafana': 3000}[group]
        inventory['all']['children'].setdefault(group, {'hosts': {}})['hosts'][name] = host
        vms[role] = {'ip': addresses[key_name], 'processors': cpus, 'memory_mb': memory}
    inventory['all']['children']['monitoring'] = {'children': {g: {} for g in ['prometheus', 'loki', 'grafana']}}
    tfvars = {'vmrest_endpoint': 'http://127.0.0.1:8697/api', 'vm_directory': values['VM_DIRECTORY'],
        'base_vm_name': values.get('BASE_VM_NAME', 'ubuntu-base'), 'vm_prefix': prefix, 'vms': vms,
        'gateway': values['LAN_GATEWAY'], 'bridge_vnet': values.get('VM_BRIDGE_VNET', 'VMnet0'), 'ssh_public_key_file': values['VM_SSH_KEY'] + '.pub'}
    for filename, data in [('inventory.json', inventory), ('lab.tfvars.json', tfvars)]:
        path = runtime / filename
        path.touch(mode=0o600, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))
        path.chmod(0o600)
    print('Generated 10 VM addresses, Terraform settings and private Ansible inventory; credentials hidden.')
    print('Grafana: http://' + addresses['GRAFANA_IP'] + ':3000')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env', type=Path, default=Path(__file__).with_name('.env'))
    parser.add_argument('--detect-network', action='store_true')
    args = parser.parse_args()
    try:
        generate(Path(__file__).resolve().parents[2], args.env.resolve(), args.detect_network)
    except (ValueError, KeyError, OSError):
        raise SystemExit('Invalid or missing private lab/deployment configuration; values hidden.') from None
