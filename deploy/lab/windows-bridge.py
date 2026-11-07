"""Invoke the scoped Windows bridge helper from WSL after managed VMs stop."""
import base64
import json
import re
import subprocess
from pathlib import Path

runtime = Path(__file__).with_name('.runtime') / 'lab.tfvars.json'
settings = json.loads(runtime.read_text())
vnet = settings.get('bridge_vnet', 'VMnet0')
if vnet == 'VMnet0':
    raise SystemExit(0)
match = re.fullmatch(r'VMnet([0-9]+)', vnet)
if not match or int(match[1]) in (0, 1, 8) or not 2 <= int(match[1]) <= 19:
    raise SystemExit('Choose a dedicated bridge between VMnet2 and VMnet19, excluding VMnet8')
script = Path(__file__).with_suffix('.ps1').read_text()
command = '& {\n' + script + '\n} -Gateway ' + settings['gateway'] + ' -Vnet ' + match[1] + ' -Prefix ' + settings['vm_prefix']
encoded = base64.b64encode(command.encode('utf-16le')).decode()
subprocess.run(['/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', '-NoProfile',
                '-EncodedCommand', encoded], check=True)
