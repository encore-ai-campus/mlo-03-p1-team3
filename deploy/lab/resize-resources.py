"""Apply only CPU/RAM changes to existing managed VMs; retain networks and disks."""
import json
import os
import subprocess
from pathlib import Path

from configure import ROLES


def validate_changes(plan):
    selected = []
    for item in plan.get('resource_changes', []):
        actions = item['change']['actions']
        if actions in (['no-op'], ['read']):
            continue
        if (item.get('mode') != 'managed' or item['type'] != 'vmworkstation_virtual_machine'
                or item['name'] != 'server' or actions != ['update']):
            raise ValueError('Resource resize refuses creation, deletion or non-VM changes')
        before, after = item['change']['before'], item['change']['after']
        keys = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
        if not keys <= {'processors', 'memory', 'state'}:
            raise ValueError('Resource resize refuses changes to paths, disks or VM identity')
        if after['state'] != 'on':
            raise ValueError('Resource resize must leave every selected VM powered on')
        selected.append(item)
    return selected


def main():
    os.umask(0o077)
    root = Path(__file__).resolve().parents[2]
    runtime = root / 'deploy/lab/.runtime'
    variables = runtime / 'lab.tfvars.json'
    config = json.loads(variables.read_text())
    for role, _ip, _group, processors, memory in ROLES:
        if role not in config['vms']:
            raise ValueError('Existing VM role missing; configure explicitly before resizing')
        config['vms'][role].update(processors=processors, memory_mb=memory)
    variables.write_text(json.dumps(config, indent=2))
    prefix = ['terraform', '-chdir=' + str(root / 'deploy/terraform/lab')]
    planfile = runtime / 'resources.tfplan'

    def run(args):
        return subprocess.run(args, capture_output=True, text=True, check=True)

    def plan():
        run(prefix + ['plan', '-input=false', '-out=' + str(planfile),
                      '-var-file=' + str(variables), '-var=power_state=on'])
        return validate_changes(json.loads(run(prefix + ['show', '-json', str(planfile)]).stdout))

    changes = plan()
    if not changes:
        print('No CPU/RAM changes required; no VM stopped.')
        return
    for item in changes:
        print('Resize role: ' + item['index'], flush=True)
    vmrun = '/mnt/c/Program Files/VMware/VMware Workstation/vmrun.exe'
    stopped = []
    try:
        for item in changes:
            path = item['change']['before']['path']
            if item['change']['before']['state'] == 'on':
                run([vmrun, 'stop', path, 'soft'])
                stopped.append(path)
                print('Gracefully stopped one resizing VM; disk retained.', flush=True)
        refreshed = plan()
        if {x['address'] for x in refreshed} != {x['address'] for x in changes}:
            raise ValueError('Plan changed after shutdown; refusing unrelated changes')
        run(prefix + ['apply', '-input=false', '-parallelism=1', str(planfile)])
        print('CPU/RAM changes applied; selected VMs powered on; disks/network unchanged.', flush=True)
    except Exception:
        for path in stopped:
            subprocess.run([vmrun, 'start', path, 'nogui'], capture_output=True)
        raise
    finally:
        planfile.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
