"""원문 로그·비밀값 없이 Prometheus 자원과 Loki 건수만 저장한다."""

import csv
import json
import math
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import ProxyHandler, build_opener


def get_json(url):
    opener = build_opener(ProxyHandler({}))
    with opener.open(url, timeout=10) as response:  # noqa: S310 사용자가 지정한 http(s) 관측 서버만 조회
        return json.load(response)


def collect(folder, row, prometheus, loki):
    result = {"prometheus": "disabled", "loki": "disabled", "peaks": {}}
    if not row.get("started_at") or not row.get("ended_at"):
        return result | {"reason": "measurement_not_started"}
    start = datetime.fromisoformat(row["started_at"]).timestamp()
    end = datetime.fromisoformat(row["ended_at"]).timestamp()
    if prometheus:
        queries = {
            "cpu_percent": '100*(1-avg by(instance)(rate(node_cpu_seconds_total{mode="idle"}[1m])))',
            "memory_percent": "100*(1-node_memory_MemAvailable_bytes/node_memory_MemTotal_bytes)",
            "root_disk_percent": '100*(1-node_filesystem_avail_bytes{mountpoint="/",fstype!="rootfs"}/node_filesystem_size_bytes{mountpoint="/",fstype!="rootfs"})',
        }
        resources, records = {}, []
        for name, query in queries.items():
            try:
                data = get_json(prometheus + "/api/v1/query_range?" + urlencode(
                    {"query": query, "start": start, "end": end, "step": 15}))
                if data.get("status") != "success":
                    raise ValueError("query_failed")
                series = data.get("data", {}).get("result", [])
                resources[name] = data
                if not series:
                    resources[name] = {"status": "no_data"}
                for item in series:
                    instance = item["metric"].get("instance", "unknown")
                    values = [(stamp, float(value)) for stamp, value in item["values"]
                              if math.isfinite(float(value))]
                    if values:
                        result["peaks"].setdefault(name, {})[instance] = max(v for _, v in values)
                    records.extend({"metric": name, "instance": instance, "timestamp_utc": stamp,
                                    "value": value} for stamp, value in values)
            except Exception as exc:  # 관측 실패는 따로 기록하고 예외 본문은 저장하지 않는다
                resources[name] = {"status": "error", "error_type": type(exc).__name__}
        (folder / "resources.json").write_text(json.dumps(resources, indent=2), encoding="utf-8")
        with (folder / "resources.csv").open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=["metric", "instance", "timestamp_utc", "value"])
            writer.writeheader()
            writer.writerows(records)
        result["prometheus"] = "ok" if all(v.get("status") == "success" for v in resources.values()) else "incomplete"
    if loki:
        try:
            seconds = max(1, math.ceil(end - start))
            query = 'sum by(service,instance,log_type)(count_over_time({job=~".+"}[' + str(seconds) + 's]))'
            data = get_json(loki + "/loki/api/v1/query?" + urlencode({"query": query, "time": end}))
            if data.get("status") != "success":
                raise ValueError("query_failed")
            counts = [{**item["metric"], "count": int(float(item["value"][1]))}
                      for item in data.get("data", {}).get("result", [])]
            (folder / "loki-counts.json").write_text(json.dumps(counts, indent=2), encoding="utf-8")
            result["loki"] = "ok" if counts else "no_data"
        except Exception as exc:
            result["loki"] = {"status": "error", "error_type": type(exc).__name__}
    return result
