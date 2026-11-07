"""Grow managed database boot disks to 40 GiB while powered off; never shrink."""
import json
import re
import subprocess
from pathlib import Path, PureWindowsPath

ROLES = {'mariadb-master', 'mariadb-replica', 'mongodb'}
TOOLS = '/mnt/c/Program Files/VMware/VMware Workstation/'


def linux_path(path):
    return Path(subprocess.check_output(['wslpath', '-u', str(path)], text=True).strip())


def main():
    module = Path(__file__).resolve().parents[1] / 'terraform/lab'
    state = json.loads(subprocess.check_output(['terraform', '-chdir=' + str(module), 'show', '-json'], text=True))
    running = subprocess.check_output([TOOLS + 'vmrun.exe', 'list'], text=True).lower()
    for resource in state['values']['root_module']['resources']:
        if resource.get('mode') != 'managed' or resource['type'] != 'vmworkstation_virtual_machine' or resource.get('name') != 'server' or resource.get('index') not in ROLES:
            continue
        vmx_win = resource['values']['path']
        if vmx_win.lower() in running:
            raise RuntimeError('Database VM must be powered off before disk expansion')
        vmx = linux_path(vmx_win)
        disks = re.findall(r'^(?:scsi|sata|nvme)\d+:\d+\.fileName\s*=\s*"([^"]+\.vmdk)"', vmx.read_text(), re.M)
        if len(disks) != 1:
            raise RuntimeError('Expected exactly one database boot disk')
        disk_win = PureWindowsPath(vmx_win).parent / disks[0]
        # Monolithic sparse VMDKs contain binary disk data after the header.
        # Read only the bounded descriptor region, never the entire disk.
        with linux_path(disk_win).open('rb') as stream:
            descriptor = stream.read(65536).decode('ascii', errors='ignore')
        sectors = sum(int(x) for x in re.findall(r'^RW\s+(\d+)\s+', descriptor, re.M))
        if not sectors:
            raise RuntimeError('Disk capacity could not be verified')
        if sectors * 512 < 40 * 1024**3:
            subprocess.run([TOOLS + 'vmware-vdiskmanager.exe', '-x', '40GB', str(disk_win)], check=True, capture_output=True)
        print(resource['index'] + ': virtual disk at least 40 GiB; existing data preserved', flush=True)


if __name__ == '__main__':
    main()
