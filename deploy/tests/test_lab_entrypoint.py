"""An install on an existing deployment must not regenerate its network settings."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1]


class ExistingDeploymentTests(unittest.TestCase):
    def test_install_reuses_inventory_after_fallback_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lab = root / 'deploy/lab'
            runtime = lab / '.runtime'
            runtime.mkdir(parents=True)
            shutil.copy(DEPLOY / 'lab.sh', root / 'deploy/lab.sh')
            shutil.copy(DEPLOY / 'lab/configure.py', lab / 'configure.py')
            (lab / '.env').write_text('LAB_REPO=/unused\nLAN_CIDR=192.168.0.0/24\nLAN_GATEWAY=192.168.0.1\nFALLBACK_LAN_CIDR=192.168.219.0/24\nFALLBACK_LAN_GATEWAY=192.168.219.1\n')
            inventory = runtime / 'inventory.json'
            original = b'{"all":{"hosts":{"nginx":{"ansible_host":"192.168.219.191"}}}}'
            inventory.write_bytes(original)
            (root / 'deploy/vm').mkdir()
            vm_env = root / 'deploy/vm/vm.env'
            vm_env.write_text('NGINX_IP=192.168.219.191\n')
            mock = root / 'bin'
            mock.mkdir()
            for name, body in [('npm', 'exit 0'), ('ansible-playbook', 'printf "%s\\n" "$@" > "$FAKE_ANSIBLE_ARGS"')]:
                p = mock / name
                p.write_text('#!/bin/sh\n' + body + '\n')
                p.chmod(0o755)
            output = root / 'ansible-args'
            environment = dict(os.environ, PATH=str(mock) + os.pathsep + os.environ['PATH'], FAKE_ANSIBLE_ARGS=str(output))
            environment.pop('PODOBANK_LAB_ENV', None)
            result = subprocess.run(['bash', str(root / 'deploy/lab.sh'), 'install'],
                                    env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(inventory.read_bytes(), original)
            self.assertEqual(vm_env.read_text(), 'NGINX_IP=192.168.219.191\n')
            self.assertEqual(output.read_text().splitlines(), ['-i', str(inventory), 'deploy/ansible/site.yml'])

    def test_second_candidate_remains_219_without_changing_first_candidate(self):
        import sys
        sys.path.insert(0, str(DEPLOY / 'lab'))
        from configure import configuration, select_network
        values = {'LAN_CIDR': '192.168.0.0/24', 'LAN_GATEWAY': '192.168.0.1',
                  'FALLBACK_LAN_CIDR': '192.168.219.0/24', 'FALLBACK_LAN_GATEWAY': '192.168.219.1'}
        preferred = select_network(values, ['192.168.0.10', '192.168.219.10'], lambda ip: True)
        self.assertEqual(preferred['LAN_CIDR'], '192.168.0.0/24')
        fallback = select_network(values, ['192.168.219.10'], lambda ip: ip == '192.168.219.1')
        self.assertEqual(fallback['LAN_CIDR'], '192.168.219.0/24')
        self.assertEqual(list(configuration(fallback)[1].values()), ['192.168.219.' + str(n) for n in range(191, 201)])


if __name__ == '__main__':
    unittest.main()
