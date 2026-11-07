#!/usr/bin/env bash
# WSL: bash deploy/lab.sh configure|plan|apply|install|observability|performance|verify
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
 install|observability|performance|verify)
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
    # Stop only managed VMs before CPU, disk or network changes; preserve existing data.
    python3 deploy/lab/power-off.py
    python3 deploy/lab/windows-bridge.py
    terraform -chdir=deploy/terraform/lab apply -input=false -auto-approve -parallelism=1 -var-file="$runtime/lab.tfvars.json" -var=power_state=off
    python3 deploy/lab/resize-db-disks.py
    terraform -chdir=deploy/terraform/lab apply -input=false -auto-approve -parallelism=1 -var-file="$runtime/lab.tfvars.json" -var=power_state=on
    ANSIBLE_TIMEOUT=60 ansible-playbook -i "$inventory" deploy/ansible/resize-db-filesystems.yml
  fi
  ;;
 install)
  if ! command -v npm >/dev/null; then python3 deploy/lab/install-node.py; fi
  export ANSIBLE_PIPELINING=true ANSIBLE_TIMEOUT=60
  ansible-playbook -i "$inventory" deploy/ansible/site.yml
  ;;
 performance)
  export ANSIBLE_PIPELINING=true ANSIBLE_TIMEOUT=60
  ansible-playbook -i "$inventory" deploy/ansible/performance.yml "${@:2}"
  ;;
 observability)
  export ANSIBLE_PIPELINING=true ANSIBLE_TIMEOUT=60
  ansible-playbook -i "$inventory" deploy/ansible/business-observability.yml
  python3 deploy/monitoring/verify.py --inventory "$inventory"
  ;;
 verify)
  python3 deploy/ansible/verify-exporters.py --inventory "$inventory"
  python3 deploy/ansible/verify-monitoring.py --inventory "$inventory"
  python3 deploy/ansible/verify-proxy-logs.py --inventory "$inventory" --read-only
  python3 deploy/monitoring/verify.py --inventory "$inventory"
  ;;
 *) echo 'Usage: bash deploy/lab.sh configure|plan|apply|install|observability|performance|verify' >&2; exit 1 ;;
esac
