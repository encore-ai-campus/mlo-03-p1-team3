"""전달 패키지의 설정·단계·성공 판정. 비밀값은 오류에도 출력하지 않는다."""

import json
import re
from pathlib import Path
from urllib.parse import urlsplit


def validate_origin(value):
    try:
        parsed = urlsplit(value)
        _ = parsed.port
        valid = (parsed.scheme in {"http", "https"} and parsed.hostname
                 and parsed.username is None and parsed.password is None
                 and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("주소는 계정·경로·쿼리가 없는 http(s)://호스트[:포트] 형식이어야 합니다.")
    return value.rstrip("/")


def parse_stages(value):
    try:
        stages = [int(part.strip()) for part in value.split(",")]
    except ValueError as exc:
        raise ValueError("단계는 쉼표로 구분한 정수입니다.") from exc
    if not stages or any(n < 1 or n > 2000 for n in stages) or stages != sorted(set(stages)):
        raise ValueError("단계는 1~2000 사이의 중복 없는 오름차순이어야 합니다.")
    return stages


def read_env(path):
    path = Path(path)
    if not path.exists():
        return {}
    values = {}
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key.strip()):
            raise ValueError(f".env {number}행 형식을 확인하세요.")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def parse_accounts(value, required):
    try:
        accounts = json.loads(value or "[]")
        valid = isinstance(accounts, list) and all(
            isinstance(a, dict) and isinstance(a.get("phone_number"), str)
            and bool(a["phone_number"]) and isinstance(a.get("password"), str)
            and bool(a["password"]) for a in accounts
        )
        if not valid or len(accounts) < required:
            raise ValueError
        if len({a["phone_number"] for a in accounts}) != len(accounts):
            raise ValueError
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError(f"read 모드는 서로 다른 시험 계정이 최소 {required}개 필요합니다. .env를 확인하세요.") from exc
    return [{"phone_number": a["phone_number"], "password": a["password"]} for a in accounts]


def resume_stages(stages, rows):
    failed = next((row["users"] for row in rows if not row["passed"]), None)
    if failed not in stages:
        raise ValueError("이전 결과에 재개할 실패 단계가 없습니다.")
    return stages[max(0, stages.index(failed) - 3):]


def evaluate_stage(row, *, seconds, max_fail_ratio, max_p95_ms):
    reasons = []
    if row.get("process_exit") != 0:
        reasons.append("Locust 실행 오류")
    if not row.get("completed") or (row.get("measured_seconds") or 0) < seconds - 0.2:
        reasons.append("측정 시간 미달")
    if (row.get("min_measured_users") or 0) < row["users"]:
        reasons.append("목표 사용자 미달")
    requests = row.get("requests", 0)
    if not requests:
        reasons.append("측정 요청 없음")
    elif row.get("failures", 0) / requests > max_fail_ratio:
        reasons.append("오류율 기준 초과")
    if row.get("p95_ms", 0) > max_p95_ms:
        reasons.append("p95 기준 초과")
    return not reasons, reasons
