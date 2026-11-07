# PodoBank business observability

Dashboard definitions live in `dashboards/*.json`. Edit these files locally, deploy
this checkout to the WSL controller, and run:

```bash
bash deploy/lab.sh observability
```

This installs only aggregate collectors and dashboard definitions, using the existing
private inventory. It does not recreate VMs, reset databases, redeploy the frontend,
or restart FastAPI. A full `bash deploy/lab.sh install` also includes these changes.
`git push` alone does not deploy: this repository has no automatic deployment runner.
Run the command from the updated checkout on the controller.

For an inventory outside the lab wrapper:

```bash
ansible-playbook -i /path/to/private/inventory.json deploy/ansible/business-observability.yml
python3 deploy/monitoring/verify.py --inventory /path/to/private/inventory.json
```

Prerequisite: existing monitoring/exporters deployment and private `deploy/vm/vm.env`
and `monitoring.env`. No new password, Python dependency or frontend/backend change.
Secrets stay on the controller; no environment files belong in Git.

## Screens

- `/d/podobank-api`: existing FastAPI screen, now with business outcomes, failure
  reasons, loan review/repayment results, HTTP methods/routes/codes and request-ID search.
- `/d/podobank-mariadb`: actual ledger, loan and card-payment counts plus replication
  health and primary/replica count differences.
- `/d/podobank-storage`: actual MongoDB collection/business-event counts, persistence
  errors and card-payment SQL/MongoDB count differences.
- `/d/podobank-nginx`: HTTP status distribution and client-disconnect (499) details.
- Ten existing dashboard UIDs are retained. Standalone business/HTTP screens are
  consolidated and retired. Long text panels are removed; context stays in tooltips.

Set the time range around the simulator run. Copy a request ID from a failure log
into the request-ID box; this filters detail logs, not summary panels. The API and
business selectors filter logs; database snapshots are system-wide current totals.
Loan-review `success/rejected` means a successful rejection action, not approval.
Transfer success writes two ledger entries (`transfer_out`, `transfer_in`). Card
payment locations are Mongo-only and are not a second event in `events.log`.

## Counts and freshness

Collectors execute on the DB VMs every 120 seconds; Prometheus scrapes node exporters
every 15 seconds. Expect roughly two minutes plus a scrape delay for a DB panel to
reflect a new operation. Values are gauges of current persisted records, not request
counters or exact selected-period increases. Snapshots older than 180 seconds, failed
collectors and unreachable nodes are excluded from count panels. A failed collection
atomically replaces the previous metrics file and removes its record-count series.
Empty data is not presented as zero or evidence of successful collection.

MariaDB uses a local Unix-socket account with SELECT on only four business tables,
read-only transactions, five-second per-statement limits and a 25-second process
limit. Primary/replica totals are gathered independently; a temporary difference can
be collection/replication timing. Equal counts do not prove identical contents.

MongoDB reuses the existing metrics account, adding `find` on only `events_bronze`
and `card_payment_locations`. Counts use the `_id_` index; business aggregation has
fixed event/outcome labels and a five-second server limit. This grouping can become
expensive as events accumulate; monitor collector duration/failures before increasing
load or retention. Queries never return customer records. Database transactions,
event file writes and Mongo inserts are separate operations: Loki event success does
not guarantee Mongo persistence. `mongodb_write_failed` and `event_log_write_failed`
are shown separately. Aggregate totals are not per-request reconciliation.

## Durable provisioning

Grafana reads JSON files from `/var/lib/grafana/dashboards/podobank` every 30 seconds.
UIDs are stable, existing unrelated dashboards are left alone, and `disableDeletion`
protects provisioned dashboards if their source disappears. UI saving is disabled
for managed dashboards: change JSON and rerun Ansible. Source changes overwrite the
same managed dashboards. Existing Grafana data storage is not deleted.

`build-dashboards.py` regenerates integrated service panels and navigation links; review the resulting JSON before deployment. Restart/polling does
not restore deleted Prometheus/Loki history. The dashboards can survive while their
underlying data expires.

Official references:
- [Grafana provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/)
- [Loki JSON and regexp queries](https://grafana.com/docs/loki/latest/query/log_queries/)
- [Node exporter textfile collector](https://github.com/prometheus/node_exporter#textfile-collector)
- [MongoDB countDocuments](https://www.mongodb.com/docs/manual/reference/method/db.collection.countDocuments/)

The consolidation migration removes only `podobank-business` and `podobank-http`
from the managed provider. It checks for unexpected JSON files, briefly enables
provisioning deletion to retire those two screens, and restores deletion protection
in an Ansible `always` block. Other dashboard/data-source/storage records are retained.
