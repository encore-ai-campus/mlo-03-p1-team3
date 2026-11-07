"""Podobank 단계별 실행·중단·재개·기록. 비밀값은 명령줄이나 산출물에 쓰지 않는다."""

import argparse
import csv
import importlib.util
import json
import math
import os
import platform
import signal
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from handoff_common import (evaluate_stage, parse_accounts, parse_stages, read_env,
                            resume_stages, validate_origin)
from observability import collect, get_json

ROOT = Path(__file__).resolve().parent
CHILD = None


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def save_reports(folder, manifest):
    rows = manifest["stages"]
    manifest["updated_at"] = datetime.now(UTC).isoformat()
    manifest["last_passed_users"] = next((r["users"] for r in reversed(rows) if r["passed"]), None)
    manifest["first_failed_users"] = next((r["users"] for r in rows if not r["passed"]), None)
    write_json(folder / "manifest.json", manifest)
    columns = ["users", "passed", "requests", "failures", "rps", "p50_ms", "p95_ms", "p99_ms",
               "peak_users", "min_measured_users", "measured_seconds", "reason"]
    with (folder / "summary.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    lines = ["# Podobank Locust 결과", "", f"대상: {manifest['host']} / 프로필: {manifest['profile']}",
             "", f"마지막 통과: {manifest['last_passed_users']}명 / 첫 실패: " + (str(manifest["first_failed_users"]) + "명" if manifest["first_failed_users"] is not None else "없음"),
             "", "이 수치는 이번 조건에서 확인한 단계이며 시스템의 절대 최대 동시 접속 수가 아닙니다.",
             "", "| 사용자 | 판정 | 요청 | 실패 | RPS | p95 ms | 유지 초 |", "|---|---|---|---|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['users']} | {'통과' if row['passed'] else '실패'} | {row.get('requests', 0)} | {row.get('failures', 0)} | {row.get('rps', 0):.2f} | {row.get('p95_ms', 0):.1f} | {row.get('measured_seconds') or 0:.1f} |")
        if row.get("failure_reasons"):
            lines.append("\n실패 사유: " + ", ".join(row["failure_reasons"]) + "\n")
    lines += ["", "health는 DB 준비 상태 부하이며 실제 금융 조회 용량을 뜻하지 않습니다.",
              "read는 로그인 뒤 조회만 수행하지만 로그인 세션·접속 로그는 생성됩니다.",
              "서버 자원 관측 누락 여부는 manifest의 observability와 단계별 resources.json을 확인하세요."]
    (folder / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="http://192.168.219.191")
    p.add_argument("--profile", choices=["health", "read"], default="health")
    p.add_argument("--stages", default="5,20,50")
    p.add_argument("--seconds", type=int, default=60)
    p.add_argument("--warmup", type=int, default=10)
    p.add_argument("--ramp-timeout", type=int, default=60)
    p.add_argument("--spawn-rate", type=float, default=0, help="0이면 약 10초 내 증가")
    p.add_argument("--cooldown", type=int, default=10)
    p.add_argument("--max-fail-ratio", type=float, default=0.01)
    p.add_argument("--max-p95-ms", type=float, default=500)
    p.add_argument("--prometheus-url", default="")
    p.add_argument("--loki-url", default="")
    p.add_argument("--output", type=Path, default=ROOT / "results")
    p.add_argument("--env-file", type=Path, default=ROOT / ".env")
    p.add_argument("--resume", type=Path, help="이전 결과 폴더: 실패점 3단계 전부터")
    p.add_argument("--dry-run", action="store_true", help="요청 없이 설정만 확인")
    return p


def interrupt(_signum, _frame):
    if CHILD and CHILD.poll() is None:
        CHILD.terminate()
        try:
            CHILD.wait(timeout=10)
        except subprocess.TimeoutExpired:
            CHILD.kill()
            CHILD.wait(timeout=5)
    raise KeyboardInterrupt


def main():
    global CHILD
    args = parser().parse_args()
    try:
        for key, value in read_env(args.env_file).items():
            os.environ.setdefault(key, value)
        host = validate_origin(args.host)
        prom = validate_origin(args.prometheus_url) if args.prometheus_url else ""
        loki = validate_origin(args.loki_url) if args.loki_url else ""
        stages = parse_stages(args.stages)
        configured_stages = stages[:]
        if not (1 <= args.seconds <= 3600 and 0 <= args.warmup <= 600
                and 1 <= args.ramp_timeout <= 600 and 0 <= args.cooldown <= 600
                and 0 <= args.max_fail_ratio <= 1 and args.max_p95_ms > 0
                and math.isfinite(args.max_p95_ms) and math.isfinite(args.spawn_rate)
                and args.spawn_rate >= 0):
            raise ValueError("시간·단계·판정 기준의 범위를 확인하세요.")
        if args.resume:
            previous = json.loads((args.resume / "manifest.json").read_text(encoding="utf-8"))
            if previous["host"] != host or previous["profile"] != args.profile:
                raise ValueError("재개는 이전과 같은 대상·프로필이어야 합니다.")
            configured_stages = previous["configured_stages"]
            stages = resume_stages(configured_stages, previous["stages"])
        accounts = parse_accounts(os.environ.get("PODOBANK_ACCOUNTS_JSON"), max(stages)) if args.profile == "read" else []
        for name in ("PODOBANK_WAIT_MIN", "PODOBANK_WAIT_MAX"):
            try:
                value = float(os.environ.get(name, "1" if name.endswith("MIN") else "3"))
            except ValueError as exc:
                raise ValueError("사용자 대기 시간 설정을 숫자로 입력하세요.") from exc
            if not math.isfinite(value) or value < 0.01:
                raise ValueError("사용자 대기 시간은 0.01초 이상의 유한한 값이어야 합니다.")
        if float(os.environ.get("PODOBANK_WAIT_MIN", "1")) > float(os.environ.get("PODOBANK_WAIT_MAX", "3")):
            raise ValueError("최소 대기 시간이 최대 대기 시간보다 큽니다.")
    except (ValueError, KeyError, OSError) as exc:
        print(str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError)
              else "설정·이전 결과 파일을 확인하세요.", file=sys.stderr)
        return 2
    plan = {"host": host, "profile": args.profile, "configured_stages": configured_stages,
            "selected_stages": stages, "hold_seconds": args.seconds, "warmup_seconds": args.warmup,
            "account_count": len(accounts), "max_fail_ratio": args.max_fail_ratio,
            "max_p95_ms": args.max_p95_ms, "prometheus_url": prom, "loki_url": loki}
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if importlib.util.find_spec("locust") is None:
        print("Locust가 없습니다. setup.sh 또는 requirements.txt로 설치하세요.", file=sys.stderr)
        return 2
    try:
        health = get_json(host + "/api/v1/health")
        if not isinstance(health, dict) or any(health.get(db) != "ok" for db in ("mariadb", "mongodb")):
            raise ValueError
    except Exception:
        print("사전 health 실패: /api/v1/health, MariaDB·MongoDB 연결을 확인하세요.", file=sys.stderr)
        return 2
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    folder = args.output.resolve() / stamp
    folder.mkdir(parents=True, exist_ok=False)
    manifest = plan | {"generator_hostname": socket.gethostname(), "platform": platform.platform(),
                       "started_at": datetime.now(UTC).isoformat(), "stages": []}
    save_reports(folder, manifest)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupt)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, interrupt)
    try:
        for index, users in enumerate(stages, 1):
            stage_dir = folder / f"stage-{index:03d}"
            stage_dir.mkdir()
            env = os.environ.copy()
            env.update(PODOBANK_PROFILE=args.profile, PODOBANK_TARGET_USERS=str(users),
                       PODOBANK_WARMUP=str(args.warmup), PODOBANK_HOLD_SECONDS=str(args.seconds),
                       PODOBANK_RAMP_TIMEOUT=str(args.ramp_timeout),
                       PODOBANK_STAGE_JSON=str(stage_dir / "stage.json"), PYTHONUTF8="1")
            command = [sys.executable, "-m", "locust", "-f", str(ROOT / "locustfile.py"),
                       "--host", host, "--headless", "--users", str(users), "--spawn-rate",
                       str(args.spawn_rate or max(1, math.ceil(users / 10))),
                       "--run-time", str(args.ramp_timeout + args.warmup + args.seconds + 15),
                       "--stop-timeout", "2", "--only-summary", "--exit-code-on-error", "0",
                       "--html", str(stage_dir / "locust.html")]
            print(f"진행: {users}명 / 워밍업 {args.warmup}초 / 측정 {args.seconds}초", flush=True)
            with (stage_dir / "runner.log").open("w", encoding="utf-8") as output:
                CHILD = subprocess.Popen(command, env=env, stdout=output, stderr=subprocess.STDOUT)  # noqa: S603 고정 Locust 모듈과 검증한 인자만 실행
                code = CHILD.wait()
            CHILD = None
            path = stage_dir / "stage.json"
            row = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
                "users": users, "completed": False, "reason": "missing_stage_report"}
            row["process_exit"] = code
            row["passed"], row["failure_reasons"] = evaluate_stage(
                row, seconds=args.seconds, max_fail_ratio=args.max_fail_ratio,
                max_p95_ms=args.max_p95_ms)
            row["observability"] = collect(stage_dir, row, prom, loki)
            manifest["stages"].append(row)
            save_reports(folder, manifest)
            print(f"판정: {users}명 {'통과' if row['passed'] else '실패'}", flush=True)
            if not row["passed"]:
                break
            if index < len(stages):
                time.sleep(args.cooldown)
    except KeyboardInterrupt:
        manifest["interrupted"] = True
        save_reports(folder, manifest)
        print(f"중단됨. 기록: {folder}", flush=True)
        return 130
    manifest["ended_at"] = datetime.now(UTC).isoformat()
    save_reports(folder, manifest)
    print(f"결과: {folder}", flush=True)
    return 0 if manifest["stages"] and all(r["passed"] for r in manifest["stages"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
