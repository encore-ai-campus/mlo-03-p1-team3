import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('lab_config', Path(__file__).resolve().parents[1] / 'lab/configure.py')
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


class LabConfigurationTests(unittest.TestCase):
    def test_base_and_foreign_vms_are_excluded_from_power_operations(self):
        spec = importlib.util.spec_from_file_location('power_off', Path(__file__).resolve().parents[1] / 'lab/power-off.py')
        power = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(power)
        common = {'type': 'vmworkstation_virtual_machine', 'values': {'path': 'example.vmx'}}
        resources = [{**common, 'mode': 'data', 'name': 'base'},
                     {**common, 'mode': 'managed', 'name': 'foreign'},
                     {**common, 'mode': 'managed', 'name': 'server'}]
        self.assertEqual(power.managed_vm_paths({'values': {'root_module': {'resources': resources}}}), ['example.vmx'])

    def test_new_network_maps_all_ten_roles(self):
        net, ips = lab.configuration({'LAN_CIDR': '192.168.219.0/24', 'LAN_GATEWAY': '192.168.219.1'})
        self.assertEqual(str(net), '192.168.219.0/24')
        self.assertEqual(ips['NGINX_IP'], '192.168.219.191')
        self.assertEqual(ips['GRAFANA_IP'], '192.168.219.200')
        self.assertEqual(len(set(ips.values())), 10)

    def test_change_of_network_updates_every_role(self):
        _, ips = lab.configuration({'LAN_CIDR': '192.168.10.0/24', 'LAN_GATEWAY': '192.168.10.1'})
        self.assertTrue(all(v.startswith('192.168.10.') for v in ips.values()))

    def test_bad_or_colliding_networks_are_rejected(self):
        for values in [
            {'LAN_CIDR': '192.168.219.0/24', 'LAN_GATEWAY': '192.168.0.1'},
            {'LAN_CIDR': '192.168.219.0/24', 'LAN_GATEWAY': '192.168.219.191'},
            {'LAN_CIDR': '192.168.219.0/24', 'LAN_GATEWAY': '192.168.219.1', 'VM_IP_START': '250'},
            {'LAN_CIDR': '8.8.8.0/24', 'LAN_GATEWAY': '8.8.8.1'},
        ]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                lab.configuration(values)

    def test_preferred_network_is_used_when_available(self):
        values = {'LAN_CIDR': '192.168.0.0/24', 'LAN_GATEWAY': '192.168.0.1',
                  'FALLBACK_LAN_CIDR': '192.168.219.0/24', 'FALLBACK_LAN_GATEWAY': '192.168.219.1'}
        result = lab.select_network(values, ['192.168.0.10', '192.168.219.102'], lambda ip: True)
        self.assertEqual(result['LAN_CIDR'], '192.168.0.0/24')

    def test_preferred_network_failure_selects_explicit_fallback(self):
        values = {'LAN_CIDR': '192.168.0.0/24', 'LAN_GATEWAY': '192.168.0.1',
                  'FALLBACK_LAN_CIDR': '192.168.219.0/24', 'FALLBACK_LAN_GATEWAY': '192.168.219.1'}
        result = lab.select_network(values, ['192.168.219.102'], lambda ip: ip == '192.168.219.1')
        self.assertEqual(result['LAN_CIDR'], '192.168.219.0/24')
        self.assertEqual(values['LAN_CIDR'], '192.168.0.0/24')
        with self.assertRaises(ValueError):
            lab.select_network(values, ['192.168.219.102'], lambda ip: False)

    def test_generated_inventory_and_vm_environment_match(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'deploy/vm').mkdir(parents=True)
            (root / 'deploy/vm/vm.env').write_text("MARIADB_PASSWORD=example-only\n")
            lab_repo = root / 'lab-repo'; lab_repo.mkdir()
            (lab_repo / 'guest-proxy.sh').write_text('# placeholder')
            key = root / 'guest.pub'; key.write_text('ssh-ed25519 example-public-key')
            env = root / '.env'
            env.write_text('LAN_CIDR=192.168.219.0/24\nLAN_GATEWAY=192.168.219.1\n'
                           + 'LAB_REPO=' + str(lab_repo) + '\nVM_SSH_KEY=' + str(key.with_suffix(''))
                           + "\nVM_DIRECTORY='C:\\VMs'\n")
            lab.generate(root, env)
            runtime = root / 'deploy/lab/.runtime'
            inventory = json.loads((runtime / 'inventory.json').read_text())
            settings = lab.read_env(root / 'deploy/vm/vm.env')
            hosts = inventory['all']['children']
            self.assertEqual(hosts['grafana']['hosts']['podobank-grafana']['ansible_host'], settings['GRAFANA_IP'])
            self.assertEqual(inventory['all']['vars']['lan_cidr'], settings['MONGODB_CLIENT_CIDR'])
            self.assertFalse(inventory['all']['vars']['reset_databases'])
            self.assertEqual(settings['MARIADB_PASSWORD'], 'example-only')
            self.assertEqual(len(json.loads((runtime / 'lab.tfvars.json').read_text())['vms']), 10)

    def test_network_updates_preserve_quoted_private_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text("PRIVATE_SETTING='example-only-value'\nNGINX_IP=192.168.0.191\n")
            lab.update_env(path, {'NGINX_IP': '192.168.219.191'})
            result = lab.read_env(path)
            self.assertEqual(result['PRIVATE_SETTING'], 'example-only-value')
            self.assertEqual(result['NGINX_IP'], '192.168.219.191')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
