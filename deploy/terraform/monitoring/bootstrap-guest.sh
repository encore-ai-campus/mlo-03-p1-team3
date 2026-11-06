#!/usr/bin/env bash
# WSL + Windows VMware. Called only for a new, powered-off Terraform clone.
set -euo pipefail
vmrun='/mnt/c/Program Files/VMware/VMware Workstation/vmrun.exe'
if "$vmrun" list | tr -d '\r' | grep -Fxq "$VMX_WIN"; then
  echo 'Bootstrap requires the new clone to be powered off.' >&2
  exit 1
fi
vmx=$(wslpath -u "$VMX_WIN")
seed_dir="${HOME}/.config/vmware-workstation-demo/seed-${VM_ID}"
mkdir -p "$seed_dir"
chmod 700 "$seed_dir"
pubkey=$(cat "${VM_SSH_PUBLIC_KEY:-${HOME}/.config/vmware-workstation-demo/demo_ed25519.pub}")
cat > "$seed_dir/user-data" <<DATA
#cloud-config
users:
  - default
  - name: playdata
    groups: [sudo]
    shell: /bin/bash
    sudo: ALL=(ALL) NOPASSWD:ALL
    ssh_authorized_keys:
      - $pubkey
ssh_pwauth: false
disable_root: true
DATA
printf 'instance-id: %s\nlocal-hostname: %s\n' "$VM_ID" "$VM_NAME" > "$seed_dir/meta-data"
cat > "$seed_dir/network-config" <<DATA
version: 2
ethernets:
  lan:
    match: {name: enp0s17}
    dhcp4: false
    addresses: [${VM_IP}/24]
    routes: [{to: default, via: 192.168.0.1}]
    nameservers:
      addresses: [168.126.63.1, 8.8.8.8]
  management:
    match: {name: enp0s18}
    dhcp4: true
    dhcp-identifier: mac
    dhcp4-overrides: {use-routes: false, use-dns: false}
    optional: true
DATA
seed_iso="$(dirname "$vmx")/cloud-init-${VM_ID}.iso"
cloud-localds --network-config="$seed_dir/network-config" "$seed_iso" "$seed_dir/user-data" "$seed_dir/meta-data"
export SEED_WIN="$(wslpath -w "$seed_iso")" VMX_LINUX="$vmx"
python3 - <<'PY'
import os,re
from pathlib import Path
p=Path(os.environ['VMX_LINUX']); s=p.read_text()
settings={'ethernet0.connectionType':'bridged','ethernet0.vnet':'VMnet0','ethernet0.startConnected':'TRUE','ethernet1.present':'TRUE','ethernet1.startConnected':'TRUE','ethernet1.connectionType':'custom','ethernet1.vnet':'VMnet1','ethernet1.virtualDev':'e1000','ethernet1.addressType':'generated','ide1:0.fileName':os.environ['SEED_WIN'],'ide1:0.present':'TRUE','ide1:0.startConnected':'TRUE','ide1:0.deviceType':'cdrom-image'}
for key,value in settings.items():
 pattern=r'(?m)^\s*'+re.escape(key)+r'\s*=.*$'; line=f'{key} = "{value}"'
 s=re.sub(pattern,lambda m:line,s) if re.search(pattern,s) else s+'\n'+line
p.write_text(s+'\n')
print('Bridged NIC, management NIC and cloud-init seed configured.')
PY
