#!/usr/bin/env bash
# WSL: bash deploy/lab.sh configure|plan|apply|install|verify
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="${HOME}/.local/podobank-node/bin:${PATH}"
config="${PODOBANK_LAB_ENV:-deploy/lab/.env}"
LAB_REPO=$(python3 - "$config" <<'PY'
import sys
sys.path.insert(0,'deploy/lab')
from configure import read_env
print(read_env(sys.argv[1])['LAB_REPO'])
PY
)
export LAB_REPO
runtime="$(pwd)/deploy/lab/.runtime"
inventory="$runtime/inventory.json"
action="${1:-plan}"
case "$action" in
 configure|plan|apply)
  python3 deploy/lab/configure.py --env "$config" --detect-network
  ;;
 install|verify)
  if [ ! -f "$inventory" ]; then
    echo 'Existing inventory missing. Run configure explicitly before deployment.' >&2
    exit 1
  fi
  # Reuse the deployed VM addresses. A changed fallback must not retarget running VMs.
  ;;
esac
case "$action" in
 configure) exit 0 ;;
 plan|apply)
  bash "$LAB_REPO/preflight.sh"
  source "$LAB_REPO/lib/config.sh"
  lab_require_credentials
  export TF_VAR_vmrest_username="$VMWS_USERNAME" TF_VAR_vmrest_password="$VMWS_PASSWORD"
  terraform -chdir=deploy/terraform/lab init -input=false
  terraform -chdir=deploy/terraform/lab validate
  if [ "$action" = plan ]; then
    terraform -chdir=deploy/terraform/lab plan -input=false -var-file="$runtime/lab.tfvars.json" -var=power_state=on
  else
    # Stop only VMs owned by this module; refresh their cloud-init seed, then boot.
    python3 deploy/lab/power-off.py
    python3 deploy/lab/windows-bridge.py
    terraform -chdir=deploy/terraform/lab apply -input=false -auto-approve -parallelism=1 -var-file="$runtime/lab.tfvars.json" -var=power_state=off
    terraform -chdir=deploy/terraform/lab apply -input=false -auto-approve -parallelism=1 -var-file="$runtime/lab.tfvars.json" -var=power_state=on
  fi
  ;;
 install)
  if ! command -v npm >/dev/null; then python3 deploy/lab/install-node.py; fi
  export ANSIBLE_PIPELINING=true ANSIBLE_TIMEOUT=60
  ansible-playbook -i "$inventory" deploy/ansible/site.yml
  ;;
 verify)
  python3 deploy/ansible/verify-exporters.py --inventory "$inventory"
  python3 deploy/ansible/verify-monitoring.py --inventory "$inventory"
  python3 deploy/ansible/verify-proxy-logs.py --inventory "$inventory" --read-only
  ;;
 *) echo 'Usage: bash deploy/lab.sh configure|plan|apply|install|verify' >&2; exit 1 ;;
esac
