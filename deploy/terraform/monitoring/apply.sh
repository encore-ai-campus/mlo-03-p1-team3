#!/usr/bin/env bash
# First run: create powered-off clones, seed them, then boot. Later runs preserve disks.
set -euo pipefail
cd "$(dirname "$0")"
source "${VMWS_CREDENTIALS_FILE:-${HOME}/.config/vmware-workstation-demo/vmrest.env}"
export TF_VAR_vmrest_endpoint="${VMWS_ENDPOINT:-http://127.0.0.1:8697/api}"
export TF_VAR_vmrest_username="$VMWS_USERNAME" TF_VAR_vmrest_password="$VMWS_PASSWORD"
terraform init -input=false
if [[ "$(terraform state list 2>/dev/null | grep -c '^terraform_data.bootstrap\[' || true)" != 3 ]]; then
  terraform apply -input=false -auto-approve -parallelism=1 -var=power_state=off
fi
terraform apply -input=false -auto-approve -parallelism=1 -var=power_state=on
