"""Read back real traces through the provisioned Grafana data source."""
import argparse
import base64
import json
import re
import shlex
import subprocess
import time
import urllib.request
from pathlib import Path


def get(url, headers):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as response:
        return json.load(response)


def all_spans(value):
    if isinstance(value, dict):
        for key, inner in value.items():
            if key == "spans":
                yield from inner
            else:
                yield from all_spans(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from all_spans(inner)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--trace-id", required=True)
    parser.add_argument("--client-spans", type=Path)
    args = parser.parse_args()
    if not re.fullmatch("[0-9a-f]{32}", args.trace_id):
        parser.error("invalid trace id")
    inventory = json.loads(subprocess.check_output(
        ["ansible-inventory", "-i", args.inventory, "--list"], text=True))
    host = inventory["grafana"]["hosts"][0]
    grafana = "http://" + inventory["_meta"]["hostvars"][host]["ansible_host"] + ":3000"
    private = Path(__file__).resolve().parents[1] / "vm" / "monitoring.env"
    password = None
    for line in private.read_text().splitlines():
        if line.startswith("GRAFANA_ADMIN_PASSWORD="):
            password = shlex.split(line.split("=", 1)[1])[0]
    if not password:
        raise RuntimeError("GRAFANA_ADMIN_PASSWORD not configured")
    headers = {"Authorization": "Basic " + base64.b64encode(("admin:" + password).encode()).decode()}
    source = get(grafana + "/api/datasources/uid/podobank-tempo", headers)
    assert source["type"] == "tempo"
    print("PASS: Tempo data source provisioned in Grafana")
    if args.client_spans:
        payload = {
            "url": "http://127.0.0.1:4318/v1/traces", "method": "POST", "body_format": "json",
            "body": json.loads(args.client_spans.read_text()), "status_code": 200,
        }
        result = subprocess.run([
            "ansible", "-i", args.inventory, "loki", "-b", "-m", "ansible.builtin.uri",
            "-a", json.dumps(payload),
        ], check=False, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError("Client timing export failed")
        print("PASS: external request timing exported")
    url = grafana + "/api/datasources/proxy/uid/podobank-tempo/api/traces/" + args.trace_id
    for attempt in range(20):
        try:
            result = get(url, headers)
            spans = list(all_spans(result))
            names = {item["name"] for item in spans}
            if {"db.acquire", "db.query", "auth.resolve_session", "money.execute",
                "events.file_write", "events.mongodb_insert", "threadpool.wait"} <= names:
                break
        except Exception:
            if attempt == 19:
                raise
        time.sleep(2)
    else:
        raise RuntimeError("Expected application spans not found")
    print("PASS: real transfer trace queried through Grafana; spans=" + str(len(spans)))
    print("Span names: " + ", ".join(sorted(names)))
    print("Grafana: " + grafana + "/explore")
    print("Trace ID: " + args.trace_id)


if __name__ == "__main__":
    main()
