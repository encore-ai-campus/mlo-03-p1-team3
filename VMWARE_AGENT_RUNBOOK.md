# Windows + WSL VMware Automation: Agent Runbook

Analyzed on 2026-11-05 (Asia/Seoul). This document describes the existing host-specific implementation, not a portable installation recipe.

## Start here

**Current test reset policy:** the full `site.yml` installation now defaults to `RESET_DATABASES=true`. It stops existing API writers, drops/recreates only the MariaDB `podobank` database, clears MongoDB `podobank`, and then recreates the schema/seed/indexes during API deployment. MariaDB replicas receive the reset through replication. This supersedes older preservation statements below. `database-access.yml` explicitly disables reset because it only updates connectivity. Loki/file logs and monitoring data are not erased. After a DB reset, existing simulator runtime state must be reconciled before reusing personas. The reset policy was executed and verified on 2026-11-06: application databases were empty before probes, all ten Ansible hosts completed without failures, Korean timestamps were verified on real signup/deposit requests, and old Loki request IDs were absent. One verification customer and one deposit ledger record remain.


### Monitoring extension (2026-11-06)

The deployment now includes ten VMs. Terraform module `deploy/terraform/monitoring` manages the three monitoring clones: Prometheus `192.168.0.198:9090`, Loki `192.168.0.199:3100`, and Grafana `192.168.0.200:3000`. All three use a bridged VMnet0 primary NIC and a VMnet1 management NIC. The existing seven application/database VMs are not recreated by this module. Preserve the controller's Terraform state; state and VM disks are not Git artifacts. The provider's clone description is kept equal to the base template description because version 2.0.1 cannot reliably update that field.

`deploy/ansible/monitoring.yml` installs the services and provisions both Grafana data sources. Node exporters run on all ten VMs. `alloy.yml` installs collectors on nginx, HAProxy and both FastAPI VMs. FastAPI retains event/application file collection and service journal collection. Nginx access/error files use `service="nginx"`, `instance=<nginx inventory name>` and `log_type="access"|"error"`; its journal uses `log_type="service"`. HAProxy enables `log stdout format raw local0`, `log global` and `option httplog`, so systemd captures real HTTP request logs; Alloy sends its journal with `service="haproxy"`, `instance=<HAProxy inventory name>`, `log_type="service"`. HTTP bodies, cookies and authorization headers are not added to these proxy log formats. Existing log formats still include request URLs.

File readers use built-in `file_match` with a 10-second discovery interval so log files created after Alloy starts are discovered. Existing component names/positions are retained. Nginx readers start at the end on first installation; API readers retain their existing behavior. No DB reset or data deletion is part of standalone Alloy deployment. Packages are installed only if absent; repeat runs do not implicitly upgrade them.

From the WSL deployment controller, install/reapply only the collectors and verify real request collection:

```bash
ANSIBLE_TIMEOUT=60 ansible-playbook -i inventory.json deploy/ansible/alloy.yml
python3 deploy/ansible/verify-proxy-logs.py --inventory inventory.json
```

The verifier sends real health requests through nginx/HAProxy to both API nodes, invalid logins for randomly generated nonexistent accounts, and one oversized health request that nginx rejects with HTTP 413. It queries Loki for nginx access/error logs, HAProxy HTTP journal logs and both API nodes' application/event/service logs. It does not call financial write APIs or insert log lines into production files. The checks intentionally leave failed-login events and nginx rejection logs. The controller inventory stays private; the verifier never prints it.

Set `LOKI_PUSH_URL=http://192.168.0.199:3100/loki/api/v1/push` in private `deploy/vm/vm.env`. Copy `monitoring.env.example` to private `deploy/vm/monitoring.env` and configure `GRAFANA_ADMIN_PASSWORD`; this password is copied only to the Grafana VM's private `/etc/grafana/podobank.env`. Grafana login user is `admin`. That environment variable bootstraps a new Grafana database; changing it later does not automatically rotate an existing account password. No credential value belongs in Git or documentation.

From the existing WSL controller repository, use:

```bash
bash deploy/monitoring.sh --verify
```

The wrapper validates inventory/settings, applies Terraform, applies Ansible, then verifies Prometheus targets, Grafana data sources and the four-host log pipeline. It issues real invalid-login API requests through nginx and checks the resulting events and service journal entries in Loki for both API instances. These are intentional failed-login events for nonexistent random users, not direct database inserts. Skip `--verify` to apply with only the service readiness checks. The full application `site.yml` can include this installation with `-e monitoring_enabled=true`; leave that flag off when deploying only the original application stack.

In Grafana Explore, select Loki and query `{log_type="event"}`, `{log_type="application"}`, `{service="nginx",log_type="access"}`, `{service="nginx",log_type="error"}` or `{service="haproxy"}`. The Prometheus source supports `up` and standard `node_*` system metrics. Data sources are provisioned automatically; dashboards are not provisioned by this change. Monitoring interfaces are restricted by UFW to the assigned LAN; Loki and Prometheus currently use no application authentication, while Grafana requires login. Remote networks require an explicit network access design.

Official references: [Grafana package installation](https://grafana.com/docs/grafana/latest/setup-grafana/installation/debian/), [Loki installation](https://grafana.com/docs/loki/latest/setup/install/local/), [Alloy journal collection](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.journal/), [Alloy file discovery](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.file/), [HAProxy logging](https://docs.haproxy.org/3.0/configuration.html#8).


### Current full-stack deployment (supersedes the nginx-only preview)

Credential correction: the application database account and schema are `podobank`. The application password was subsequently changed to the value in the user's local `backend/.env`, replacing the separately generated application password used during initial setup. The master user change replicated to the replica; both API environment files and all installed role-installer environment files were synchronized, and both backend services were restarted. No password value is recorded here.

The seven bridged VMs are now deployed: nginx `.191`, HAProxy `.192`, API `.193/.194`, MariaDB master `.195`, replica `.196`, and MongoDB `.197`, all on `192.168.0.0/24`. Open `http://192.168.0.191/docs` for the real PodoBank backend API. This branch contains no frontend build; `/` remains an installation verification page.

Controller deployment directory: `/home/playdata/podobank-full-deploy`. Ansible entry point: `deploy/ansible/site.yml`, inventory: `inventory.json`, log: `full-deploy.log`. The playbook copies and executes the existing `deploy/vm/*.sh` installers. The actual `vm.env` is a symlink to the private `.env`; both public addresses and inventory are checked before deployment. An old separate `vm.env` initially retained `192.168.56.*` and caused replica connection failure; replacing that stale configuration resolved the failure. Never package private environment files when transferring public installer sources.

The completed Ansible run reported zero failed/unreachable hosts for all seven VMs. External Mac HTTP checks returned 200 for `/docs` and `/api/v1/health` on both APIs, HAProxy and nginx; health reported both MariaDB and MongoDB `ok`. Nginx `/openapi.json` identified `PodoBank API` with 23 paths. Eight requests alternated `X-Backend-Server: api-1` and `api-2`. Master and replica both had migrations `0001_init`, `0002_seed`, 3 loan products and 30 merchants; the replica was read-only and both replication threads passed checks. This does not verify automatic DB failover or application read splitting.

Backend files are installed under `/opt/podobank/backend` with service `podobank-api`; minimal preview services were disabled. API package installation uses the existing requirements file.

#### LAN database clients (verified 2026-11-05)

MariaDB master `.195` has a `podobank` account matching `192.168.0.%`, with privileges scoped to `podobank.*`; the API-specific accounts remain. MongoDB `.197` now has authorization enabled. Its `podobank` user has `readWrite` on the `podobank` database, and UFW permits port `27017` only from `192.168.0.0/24`. Both application services use the private `MARIADB_PASSWORD` value for their respective `podobank` accounts. The separate MongoDB deployment-admin password is stored only in the private `vm.env`/`.env` and is not needed in Compass.

Use MySQL Workbench with host `192.168.0.195`, port `3306`, user `podobank`, and default schema `podobank`. Use MongoDB Compass with host `192.168.0.197`, port `27017`, user `podobank`, and authentication database `podobank`. The Mac at `192.168.0.17` reached both database ports; API health checks also reported MariaDB and MongoDB `ok` through both API VMs and nginx. The Ansible playbook `deploy/ansible/database-access.yml` was run twice successfully; it reapplies account/firewall settings without dropping database contents. A client address change within `192.168.0.0/24` does not require another grant update.

### Active browser demo (2026-11-05)

**Current endpoint after bridge migration: `http://192.168.0.191`.** The nginx VM's ethernet0 is now bridged, with guest static address `192.168.0.191/24`, gateway `192.168.0.1`, and DNS `168.126.63.1` / `8.8.8.8`. Its host-only management NIC remains at `192.168.222.133`. The following tunnel description records the earlier access method; the direct LAN endpoint needs neither that tunnel nor the Windows nginx proxy.

Guest network configuration: `/etc/netplan/60-browser-nginx.yaml`, matched to the current VM's NIC MACs. Cloud-init network regeneration is disabled via `/etc/cloud/cloud.cfg.d/99-browser-network.cfg`. Previous guest network/site files are backed up in `/root/browser-nginx-before-bridge/`; the previous VMX is saved in `browser-nginx/ubuntu24-browser-nginx.vmx.before-bridge`. The VM was gracefully stopped before editing VMX and booted afterward; static address and default route were confirmed after boot. `nginx -t` passed, and direct Mac requests to `/health` and `/` succeeded with HTTP 200 and the expected VM header/page marker. The browser was opened at the new endpoint.

`browser-nginx/ansible/browser-site.json` now uses the direct URL and `server_name 192.168.0.191 localhost`; `connection.json` records the new address. `configure-bridge-guest.py` records guest changes for this existing VM, with its current MAC addresses; it is not a generic clone provisioning script. The original Terraform/bootstrap source still prepares NAT clones, so rebuilding this VM requires incorporating the bridged/static network provisioning explicitly. HAProxy/FastAPI have not been installed or connected by this nginx migration.

The persistent project `browser-nginx/` now manages VM `ubuntu24-browser-nginx` (management IP observed: `192.168.222.133`). Unlike the disposable tests, this VM was intentionally left running. Docker Desktop on the controlling Mac was stopped at the user's request.

Browser URL on that Mac: `http://127.0.0.1:8000`. Route: Mac SSH local forward → Windows nginx `127.0.0.1:18080` → guest nginx `192.168.222.133:80`. This is local browser access through SSH, not a LAN-wide Windows port 8000 listener.

Guest site: `/etc/nginx/sites-available/browser-nginx.conf`, enabled by a symlink under `sites-enabled`; document root `/var/www/browser-nginx`. The dedicated Ansible playbook is `browser-nginx/ansible/browser-site.json`. Windows proxy configuration is `browser-nginx/windows-proxy/nginx-1.31.8/conf/nginx.conf`. `connection.json` and `installed-tools.json` in the project record the endpoint and Windows nginx version/source.

The external Mac check `curl http://127.0.0.1:8000/health` returned HTTP 200, `X-Served-By: ubuntu24-browser-nginx`, and `browser-nginx-ok`. The page contains `browser-nginx-live`; Ansible site deployment reported `ok=8 changed=6 unreachable=0 failed=0`. The default browser was opened at the local URL.

If the local SSH tunnel exits, re-create it after checking that local port 8000 is free:

```bash
ssh -fNT -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L 127.0.0.1:8000:127.0.0.1:18080 playdata
```

The tunnel and Windows nginx were started for the current session, not configured as reboot-persistent services. If the VM's DHCP address changes, regenerate inventory and update the Windows nginx upstream before testing/reloading. Do not rerun the generic guest configuration after deploying this site without reviewing its different document root.

Connect from the controlling machine:

```bash
ssh playdata
cd /mnt/c/Users/Playdata/Documents/temp/vmware-workstation-wsl-example
```

The SSH alias currently resolves to user `playdata` at `192.168.0.11:22`. The remote shell is Bash inside WSL2, not Windows PowerShell. If the alias is unavailable, use `ssh playdata@192.168.0.11` from the same reachable network.

Before changing anything, read this runbook and the remote project's `README.txt`. Inspect the current Terraform state and API inventory. Preserve the base VM and any existing clone unless the task explicitly authorizes changing them.

## Host and filesystem map

| Component | Location or role |
| --- | --- |
| Windows host | `MLO-03-WONJU0516` |
| WSL account | `/home/playdata` |
| WSL distribution used by SSH automation | `Ubuntu-24.04` |
| Shared project, Windows path | `C:\Users\Playdata\Documents\temp\vmware-workstation-wsl-example` |
| Shared project, WSL path | `/mnt/c/Users/Playdata/Documents/temp/vmware-workstation-wsl-example` |
| Windows Workstation tools | `/mnt/c/Program Files/VMware/VMware Workstation/` |
| Existing clone target | `C:\Users\Playdata\Documents\Virtual Machines\ubuntu24-tf-fixed\ubuntu24-tf-fixed.vmx` |
| Base VMX | `base/ubuntu-base.vmx`, relative to the shared project |
| WSL private configuration | `/home/playdata/.config/vmware-workstation-demo/` |
| Windows DHCP leases | `/mnt/c/ProgramData/VMware/vmnetdhcp.leases` |
| Windows SSH automation | `C:\Users\Playdata\Documents\temp\wsl2-ssh-forward.ps1` |

The project is on the Windows filesystem and is visible through `/mnt/c` in WSL. These are two views of the same files. Workstation requires Windows-accessible VM disks and ISO files; use `wslpath -w` for arguments passed to Windows tools, and `wslpath -u` for paths read from Terraform.

## Responsibilities and connectivity

1. An external agent connects to WSL over SSH.
2. Linux Terraform calls Windows `vmrest` at `http://127.0.0.1:8697/api`.
3. Terraform clones the registered base and controls CPU, memory, power and destruction.
4. A Terraform `local-exec` bootstrap prepares the powered-off clone's cloud-init ISO and management NIC.
5. Ansible connects to the running Ubuntu guest, installs nginx, deploys a page and checks HTTP.

Windows Workstation runs the VMs. Windows GUI interaction is unnecessary for the implemented registration and lifecycle workflow.

Observed `.wslconfig`: mirrored networking, 4 GB memory, 4 processors, 1 GB swap, GUI applications disabled, nested virtualization disabled, and `autoMemoryReclaim=dropCache`. Do not change these merely to run the example.

VMnet8 provides NAT internet access; VMnet1 provides host-only management access. If WSL cannot connect directly to the guest's management IP, generated inventory uses `guest-proxy.sh` and `tcp-relay.ps1`. The relay opens a Windows TCP client connection and forwards SSH over standard input/output; it does not create a listening port.

## Credentials and private artifacts

Existing scripts source `~/.config/vmware-workstation-demo/vmrest.env`. Required variable names are `VMWS_USERNAME` and `VMWS_PASSWORD`; optional names are `VMWS_ENDPOINT` and `VMWS_CREDENTIALS_FILE`. Terraform receives `TF_VAR_vmrest_endpoint`, `TF_VAR_vmrest_username` and `TF_VAR_vmrest_password` from the wrapper.

Do not print or copy credentials, private keys, Terraform state or generated inventory into chat, logs, source control or documentation. Do not enable shell tracing around credential loading. The legacy credential file already exists; this analysis did not read its values. For new secret configuration, follow the repository rule to use `.env` and add only fake examples to `.env.example`; adapt the credential-file override rather than duplicating real values.

Other existing private artifacts include `demo_ed25519`, its public key, `inventory.json`, per-VM known-host files and seed directories. The SSH key must remain in WSL with restrictive permissions. `DEMO_USER` overrides the inventory username only; bootstrap scripts still explicitly create `playdata`.

## Existing commands

Run from the shared project directory, after reviewing the target state:

```bash
# Read current API VM inventory using existing credentials.
bash api-status.sh

# Read the current Terraform state; also runs terraform init.
bash terraform-vm.sh status

# Create/bootstrap the configured clone if necessary, then power it on.
bash terraform-vm.sh on

# Discover its management IP, connect over SSH, configure nginx and test HTTP.
bash configure-guest.sh

# Apply desired power-off state.
bash terraform-vm.sh off

# Destroy the resources tracked by this project state; interactive confirmation.
bash terraform-vm.sh destroy
```

`on` and `off` use automatic Terraform approval. `off` is a Terraform apply, so review the plan/state first rather than assuming it is a pure power command. `status` can expose state details; inspect locally and report only necessary non-secret findings. `run-demo.sh` is a compatibility wrapper for `terraform-vm.sh`.

The destroy wrapper saves resource metadata, runs Terraform destruction, then invokes `cleanup-guest.py`. Cleanup removes the exact generated seed ISO and an empty clone directory only after checking that VMX and VMDK files are gone. Direct `terraform destroy` bypasses this cleanup. The wrapper does not remove WSL seed directories or known-host files.

## File guide

| File | Behavior |
| --- | --- |
| `terraform/main.tf` | Pins `elsudano/vmworkstation` to `2.0.1`; finds base `ubuntu24-base`; manages clone `ubuntu24-tf-fixed`, 2 vCPU, 2048 MB RAM; invokes guest bootstrap |
| `terraform/variables.tf` | API endpoint, username, sensitive password and validated `on`/`off` power state |
| `terraform-vm.sh` | Initializes Terraform; performs first OFF apply before ON; wraps destruction and cleanup |
| `bootstrap-guest.sh` | Refuses bootstrap of a running clone; generates per-VM cloud-init seed; attaches ISO and VMnet1 NIC |
| `guest-inventory.py` | Reads Terraform state and VMX management MAC; matches DHCP lease; chooses direct SSH or proxy; writes private inventory |
| `configure-guest.sh` | Retries inventory discovery up to 30 times, then runs the Ansible playbook |
| `ansible/configure-guest.yml` | Waits for SSH/cloud-init; installs nginx; deploys page; enables service; validates HTTP 200 and expected content inside guest |
| `guest-proxy.sh`, `tcp-relay.ps1` | WSL-to-Windows SSH stream relay |
| `register-base.sh`, `register-vm.py` | Register existing VMX through `/api/vms/registration`; skip an already registered Windows path |
| `prepare-cloud-init.sh` | Creates/reuses guest SSH key and builds the base seed ISO |
| `create-base-template.sh` | Converts extracted VMDK when needed and writes the base VMX; contains a fixed project path |
| `prepare-base.sh` | Rewrites/prepares base VMX, registers base, boots it, waits 45 seconds and requests soft shutdown |
| `setup-wsl-tools.sh` | Installs Terraform, Ansible and image utilities; modifies apt repositories and packages |

Base preparation is a one-time setup path, not a routine prerequisite for each clone. Do not rerun it against an existing base without checking its state. The fixed 45-second wait does not itself verify cloud-init completion.

## Isolation for multiple agents

The current project has one default state, one clone name/path and one shared `inventory.json`. Concurrent lifecycle or configuration runs can target the same VM or overwrite inventory. Serialize work on the default project.

For an authorized independent experiment, create a separate project directory, unique clone name and Windows VMX path, and separate Terraform state. Preserve resource addresses expected by helper scripts, or update those helpers consistently. Inventory/private-directory paths are hardcoded in several scripts, so state isolation alone is insufficient for concurrent runs. Inspect and adapt those paths before running agents concurrently. Never copy an existing Terraform state into a new experiment as its starting state.

## Known pitfalls and recovery clues

- API endpoint must include `/api`; missing it previously caused provider failures.
- The provider uses `vmworkstation_virtual_machine`, with `denomination` and `sourceid` as shown in the current source. Do not substitute names from incompatible examples.
- Keep a nonempty description and the existing VMnet8 custom-network approach; earlier provider NIC recreation failed.
- Preserve the OFF-bootstrap-ON sequence. Editing VMX or attaching bootstrap media while the clone runs is unsupported by this script.
- Provider IP output such as `0.0.0.0/0` is not a usable guest address. Inventory matches the VMnet1 MAC to VMware DHCP leases instead.
- A fresh clone can initially expose the base SSH host key before cloud-init regenerates it. A live retest encountered `REMOTE HOST IDENTIFICATION HAS CHANGED` in the clone-specific known-host file. Verify the isolated clone ID and DHCP/MAC mapping before removing only that clone's stale host entry with `ssh-keygen -f <clone-specific-known-hosts> -R <guest-IP>`; do not disable host verification globally.
- The inventory module docstring mentions VMware Tools, but the implementation uses DHCP leases.
- `configure-vmrest-bridge.ps1` and `remove-vmrest-bridge.ps1` are legacy NAT bridge helpers, not part of the current mirrored workflow. `inspect-base.sh` uses an unsupported `listRegisteredVM` command according to the existing README.
- Many scripts contain host-specific paths. Review them before relocating the project.
- The SSH forwarding script handles both NAT and mirrored modes. Its scheduled tasks are `WSL2 SSH Port Forward Refresh` and `WSL2 SSH Service Start`; `StartSsh` runs `sshd -D -e` in the foreground to keep SSH attached to a running WSL process. Its top comments still describe an older service-start approach; the executable action is authoritative.
- SSH scheduled tasks trigger at Windows user logon, not an independently verified unattended boot lifecycle. Do not restart WSL or edit these tasks during an active remote session without a recovery path.

## Evidence and verification limits

This analysis connected successfully over SSH, read the implementation and Windows WSL/SSH configuration files, and confirmed the project/private-directory filenames. It did not create, power on, configure or destroy a VM, and did not verify current scheduled-task status or current API availability.

Existing evidence is under `verification-20261105-145222/`; `verification-current.txt` points there. `RESULT.txt` records: new clone creation, API `poweredOn`, successful Ansible SSH/cloud-init/nginx/HTTP checks, a second Ansible run with `ok=6 changed=0 unreachable=0 failed=0`, destruction, and a subsequent cleanup-aware create/destroy check that removed VMX, VMDK, seed ISO and clone directory while preserving the base and original powered-off clone. Treat these as historical results, not a fresh execution by the current agent.

The archived `verify-lifecycle.sh` uses direct Terraform destruction and predates the cleanup-aware final flow. Read its results and later logs; do not blindly rerun that script as the preferred lifecycle entry point. Application-specific tests, CI integration and recovery from forced interruption remain outside that historical verification scope.

## Supporting references

### Fresh execution attempt: 2026-11-05

Latest retest at the user's request used `ANSIBLE_TIMEOUT=300` in the isolated test runner and archived the recreated test VM's stale known-host file. Creation, first configuration/HTTP assertions, second configuration (`ok=6 changed=0 unreachable=0 failed=0`), OFF apply and cleanup all passed. Cleanup reported `2 destroyed` and removed the seed ISO and clone directory. This confirms completion with a longer wait; it does not establish the underlying intermittent latency source. Shared production/example scripts were not changed.

Additional unmodified-script test (`agent-live-20261105-174854/`): creation succeeded, direct guest Ansible ping returned pong, and the first playbook passed (`ok=6 changed=2 unreachable=0 failed=0`), including HTTP assertions. The second playbook failed while waiting for privilege escalation: `Timeout (12s) waiting for privilege escalation prompt`. Power-off and cleanup succeeded; `2 destroyed`, seed ISO and clone directory removed. A separate diagnostic recreation found three successful passwordless sudo probes and four successful Ansible become probes (two with timeout 10, two with timeout 60), all returning root. This rules out a persistent missing sudo permission/password requirement in that diagnostic VM. SSH command batches took about 22 seconds and Ansible become probes took 11.6–13.4 seconds end to end; those totals include connection setup and other commands, so they do not prove sudo itself or the Windows relay caused the delay. The immediate failure mechanism is the short privilege-escalation wait; the precise intermittent latency source remains unconfirmed. Diagnostic VM cleanup also succeeded, and shared inventory was restored. No shared source scripts were changed by this test.

Retest after vmrest recovery: the API probe returned HTTP 401 (reachable), and authenticated Terraform creation succeeded. The isolated run passed Ansible configuration and HTTP checks (`ok=6 changed=2 failed=0`), then passed a second run (`ok=6 changed=0 unreachable=0 failed=0`), power-off apply, and cleanup-aware destruction (`2 destroyed`). The clone directory was absent and managed state resources were zero afterward; base and original clone VMX files remained. Shared inventory was restored. The test used `ANSIBLE_TIMEOUT=60` after a default 12-second privilege-escalation timeout. Recreating the same clone path reused its VM ID and IP, requiring removal of that verified clone's stale host-key entry. These adjustments were confined to the isolated test workflow. Logs: `agent-test-20261105-171425/`; the failed configuration attempt is preserved in `attempt-before-timeout-adjustment/`. This successful retest supersedes the earlier connectivity failure retained below.

An isolated test was attempted in `agent-test-20261105-171425/`, with a unique clone name/path and separate Terraform state. Terraform initialized successfully but blocked while reading the base VM. An unauthenticated connectivity probe (`curl --max-time 8 ... http://127.0.0.1:8697/api/vms`) timed out with HTTP code `000`; Windows process/listener queries returned no `vmrest` process or TCP 8697 listener. The apply was interrupted before VM creation. Cleanup completed with `Resources: 0 destroyed`; the isolated clone directory did not exist, and the saved shared inventory was restored. Ansible and HTTP/idempotence checks were not reached. Start the existing Windows vmrest service and confirm API connectivity before retrying. Logs remain in the isolated test directory. Historical success above does not establish current API availability.

- Existing environment writeups: [SSH access](https://naelonambul.tistory.com/207), [tools and base registration](https://naelonambul.tistory.com/208), [Terraform and Ansible workflow](https://naelonambul.tistory.com/209).
- For future implementation changes, verify version-specific behavior against the [provider source and documentation](https://github.com/elsudano/terraform-provider-vmworkstation), [Broadcom Workstation API documentation](https://developer.broadcom.com/xapis/vmware-workstation-pro-api/latest/), and [Ansible documentation](https://docs.ansible.com/). These are reference links; this file's implementation findings come from the inspected local scripts and existing verification record.
