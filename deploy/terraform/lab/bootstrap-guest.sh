#!/usr/bin/env bash
# Run only with this module's VMs powered off. Network changes preserve disks.
set -euo pipefail
vmrun='/mnt/c/Program Files/VMware/VMware Workstation/vmrun.exe'
if "$vmrun" list | tr -d '\r' | grep -Fxq "$VMX_WIN"; then
  echo 'Network configuration requires this VM to be powered off.' >&2
  exit 1
fi
vmx=$(wslpath -u "$VMX_WIN")
export VMX_LINUX="$vmx"
seed_dir=$(mktemp -d)
trap 'rm -rf "$seed_dir"' EXIT
python3 - "$seed_dir" <<'PY'
import hashlib,json,os,re,sys
from pathlib import Path
root=Path(sys.argv[1]); vmid=os.environ['VM_ID']; ip=os.environ['VM_IP']; gateway=os.environ['VM_GATEWAY']
h=hashlib.sha256(vmid.encode()).digest()
mac='00:50:56:%02x:%02x:%02x'%(h[0]&63,h[1],h[2])
network={'version':2,'ethernets':{'lan':{'match':{'macaddress':mac},'set-name':'lan0','dhcp4':False,
 'addresses':[ip+'/24'],'routes':[{'to':'default','via':gateway}],
 'nameservers':{'addresses':[gateway,'1.1.1.1']}}}}
pubkey=Path(os.environ['VM_SSH_PUBLIC_KEY']).read_text().strip()
user={'users':['default'],'ssh_authorized_keys':[pubkey],'ssh_pwauth':False,'disable_root':True}
(root/'user-data').write_text('#cloud-config\n'+json.dumps(user))
netkey=hashlib.sha256((json.dumps(network,sort_keys=True)+pubkey).encode()).hexdigest()[:12]
(root/'meta-data').write_text('instance-id: '+vmid+'-'+netkey+'\nlocal-hostname: '+os.environ['VM_NAME']+'\n')
(root/'network-config').write_text(json.dumps(network))
p=Path(os.environ['VMX_LINUX']);s=p.read_text()
settings={'ethernet0.present':'TRUE','ethernet0.connectionType':'bridged' if os.environ.get('VM_BRIDGE_VNET','VMnet0')=='VMnet0' else 'custom','ethernet0.vnet':os.environ.get('VM_BRIDGE_VNET','VMnet0'),
 'ethernet0.startConnected':'TRUE','ethernet0.addressType':'static','ethernet0.address':mac,
 'ethernet1.present':'FALSE','ide1:0.present':'TRUE','ide1:0.startConnected':'TRUE',
 'ide1:0.deviceType':'cdrom-image','ide1:0.fileName':str(p.parent/'podobank-cloud-init.iso').replace('/mnt/c/','C:/').replace('/','\\')}
for key in ['ethernet0.generatedAddress','ethernet0.generatedAddressOffset']:
 s=re.sub(r'(?m)^\s*'+re.escape(key)+r'\s*=.*\n?','',s)
for key,value in settings.items():
 pattern=r'(?m)^\s*'+re.escape(key)+r'\s*=.*$';line=key+' = "'+value+'"'
 s=re.sub(pattern,lambda _:line,s) if re.search(pattern,s) else s+'\n'+line
p.write_text(s+'\n')
PY
cloud-localds --network-config="$seed_dir/network-config" "$(dirname "$vmx")/podobank-cloud-init.iso" "$seed_dir/user-data" "$seed_dir/meta-data"
echo 'Bridged IP and cloud-init network seed updated; existing VM disk preserved.'
