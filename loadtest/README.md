# PodoBank 부하 테스트

`/Users/mokwonju/Downloads/podobank-locust` 참고 자료를 프로젝트 API에 맞춰 적용했습니다.
Locust 2.47.0은 기존 `backend/requirements.txt`에 고정되어 있습니다. 새 의존성은 없습니다.

프로젝트 루트에서 첫 상태 확인 부하를 실행합니다.

```bash
.venv/bin/python loadtest/run.py \
  --host http://192.168.219.191 --profile health \
  --stages 5,20,50 --warmup 10 --seconds 60 --cooldown 10 \
  --prometheus-url http://192.168.219.198:9090 \
  --loki-url http://192.168.219.199:3100
```

사용자마다 1~3초 대기합니다. 각 단계는 목표 인원 도달 및 준비 → 워밍업 → 통계 초기화 → 60초 측정 순서입니다.
오류율 1% 또는 p95 500ms를 초과하면 다음 단계로 올리지 않습니다. 측정 시간·인원 미달도 실패입니다.
이 수치는 초기 비교 기준이며 금융 업무의 성능 목표나 최대 용량을 의미하지 않습니다.
`--dry-run`은 요청 없이 계획만 출력합니다. Ctrl+C로 중단할 수 있습니다.

기본 health 모드는 `/api/v1/health`에서 MariaDB `SELECT 1`, MongoDB `ping`을 확인합니다.
계정·금융 거래·업무 이벤트는 생성하지 않습니다. HTTP 요청 로그와 메트릭은 발생합니다.
가상 사용자 수는 동시에 유지하는 Locust 사용자 수이며 실제 DB 계정 수나 초당 요청 수와 다릅니다.
기존 루트 `locustfile.py`는 간단한 웹 UI 테스트용으로 그대로 유지합니다.

## 로그인 조회

`--profile read`는 고객 로그인 후 세션 쿠키로 계좌 40%, 거래내역 40%, 내 정보 20%를 조회합니다.
계좌가 있는 서로 다른 시험 고객 계정이 최고 단계 인원 이상 필요합니다. 직원 계정은 사용하지 않습니다.
계정은 자동 생성하지 않습니다. 실제 값은 `loadtest/.env`의 `PODOBANK_ACCOUNTS_JSON`에만 넣습니다.
새 파일은 `.env.example`을 참고하고, 기존 `.env`는 덮어쓰지 마세요.
조회 프로필은 health 프로필의 통과와 별개로 검증해야 합니다.

## 결과와 관측

`loadtest/results/<UTC시각>/REPORT.md`, `summary.csv`, `manifest.json`을 확인합니다.
단계별 HTML·CSV, 측정 시작/종료, 실제 인원, HTTP 상태 코드, Prometheus 자원 지표, Loki 로그 건수를 저장합니다.
결과 폴더와 `.env`는 Git에서 제외합니다. 원문 업무 로그·비밀번호·쿠키를 보고서에 저장하지 않습니다.
Loki 집계는 측정 구간의 서비스/인스턴스/로그 종류별 전체 로그이므로 모니터링 트래픽도 포함할 수 있습니다.
로그 전달 지연으로 막 끝난 구간의 건수가 적게 보일 수 있습니다.
CPU 지표는 1분 rate와 15초 표본이어서 이전 구간의 영향을 받을 수 있습니다. 관측 누락은 0으로 바꾸지 않습니다.
시간은 비교를 위해 UTC로 저장하며 한국 시각은 UTC+9입니다.
서버와 다른 맥북에서 실행하면 VM 호스트와 부하 발생기가 CPU를 공유하지 않습니다.

공식 문서: [headless 실행과 종료](https://docs.locust.io/en/stable/running-without-web-ui.html),
[HttpUser 세션·이벤트 API](https://docs.locust.io/en/stable/api.html).

## 다음 단계: 100 → 200 → 400명

```bash
bash loadtest/run-next.sh
```

이전 health 테스트와 같은 대기 시간·워밍업·측정 시간·판정 기준으로 인원을 올립니다.
실패한 단계 이후에는 상승하지 않습니다. 측정 결과는 매번 별도 폴더에 저장됩니다.
계정을 생성하거나 금융 거래를 실행하지 않습니다.
`bash loadtest/run-next.sh --dry-run`으로 요청 없이 확인할 수 있습니다.
대상 주소·측정 시간 등은 마지막에 같은 CLI 옵션을 추가해서 변경할 수 있습니다.
실시간 관측: <http://192.168.219.200:3000/d/podobank-overview?from=now-15m&to=now&refresh=15s>
