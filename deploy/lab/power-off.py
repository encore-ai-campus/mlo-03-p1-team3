"""Gracefully stop only managed application VMs before changing networks."""
import json
import subprocess
from pathlib import Path, PureWindowsPath


def managed_vm_paths(state):
    return [resource['values']['path']
            for resource in state.get('values', {}).get('root_module', {}).get('resources', [])
            if resource.get('mode') == 'managed' and resource.get('type') == 'vmworkstation_virtual_machine'
            and resource.get('name') == 'server']


def main():
    module = Path(__file__).resolve().parents[1] / 'terraform/lab'
    if not (module / 'terraform.tfstate').exists():
        return
    result = subprocess.run(['terraform', '-chdir=' + str(module), 'show', '-json'],
                            capture_output=True, text=True, check=True)
    state = json.loads(result.stdout)
    vmrun = '/mnt/c/Program Files/VMware/VMware Workstation/vmrun.exe'
    running = subprocess.run([vmrun, 'list'], capture_output=True, text=True, check=True).stdout.splitlines()[1:]
    running = {str(PureWindowsPath(p.strip())).lower() for p in running}
    for path in managed_vm_paths(state):
        if str(PureWindowsPath(path)).lower() in running:
            subprocess.run([vmrun, 'stop', path, 'soft'], capture_output=True, timeout=120, check=True)
            print('Gracefully stopped one managed VM; guest disk retained.', flush=True)


if __name__ == '__main__':
    main()
