# 로그인·송금 분리 부하시험

`split_scenarios.py`는 기존 페르소나 Playwright와 별개의 서버 성능 시험이다.
기존 Locust 2.47.0의 `HttpSession`과 통계를 사용하며 새 의존성은 없다.

## 로그인 전용

```bash
.venv/bin/python loadtest/split_scenarios.py login \
  --host http://192.168.219.191 --allow-remote \
  --accounts 1000 --rates 1,2,5,10,20 --warmup 10 --seconds 60
```

계정 가입·로그아웃을 준비 단계에서 끝낸다. 측정 구간에는 로그인 요청만 보낸다.
초당 요청 수를 고정하고 최초 기준 미달 단계에서 멈춘다. 단계 사이에 조회·송금을 실행하지 않는다.
계정별 클라이언트를 유지하며 같은 계정에 동시에 요청하지 않는다.

## 사전 로그인 후 송금 흐름

```bash
.venv/bin/python loadtest/split_scenarios.py transfer \
  --host http://192.168.219.191 --allow-remote \
  --accounts 1000 --prelogin-rate 5 --rates 10,20,40,80,160,320 \
  --warmup 10 --seconds 60
```

가입·초기 입금을 준비한 뒤 초당 5명씩 로그인한다. 전원이 성공하지 않으면 송금 측정을 시작하지 않는다.
로그인 완료 후 10초 쉬고, 각 단계의 워밍업과 측정을 진행한다.
측정 흐름은 `잔액 → 받는 사람 조회 → 송금 → 잔액`이며 송금 1회당 HTTP 요청은 보통 4건이다.
측정 중 로그인·재로그인은 금지한다. 401은 세션 조건 미충족으로 판정하며 송금 한계로 해석하지 않는다.

1,000개 사전 로그인 세션은 동시에 1,000개 요청을 보낸다는 뜻이 아니다.
고정 간격으로 계정들을 순환하며 흐름을 시작한다. 기존 실행기의 첫 흐름 몰림과 사용자 재생성을 사용하지 않는다.
따라서 원본 `constant_throughput` 시험과 부하 발생 방식이 달라졌다는 점도 비교 시 고려해야 한다.

## 판정·데이터

- 오류율 1% 이하, HTTP 요청 전체 p95 500ms 이하를 기준으로 한다.
- 송금 실제 시도 TPS가 목표의 95% 미만이면 목표 부하 미달로 판정한다.
- 요청 일정 누락·작업 예외·미완료 흐름·부하 발생기 CPU 경고는 부하 전달 조건 문제로 별도 기록한다.
- 금융 요청과 로그인에 자동 재시도를 하지 않는다. 응답이 불확실한 송금은 관련 계좌를 불확실로 분류한다.
- 마지막 흐름까지 기다린 뒤 통계를 저장한다. JSON의 `window_end`와 `drained_end`를 구분한다.
  측정 구간에 시작한 흐름의 완료 응답을 포함하므로 HTTP 요청 RPS는 종료 후 완료분도 포함한다.
- 10명 중 1명의 초기 잔액은 적게 준비하며 이 그룹의 예상 잔액 부족 409는 별도로 집계한다.
- 종료 잔액 검증은 재로그인하지 않는다. 인증 실패나 불확실 계좌를 정상 검증으로 처리하지 않는다.
- 실제 시험용 계정·거래·이벤트가 생성되며 기존 DB는 초기화하지 않는다.
- 새 계정 자격 증명은 메모리에만 두고, 재사용 풀은 비공개 .env에서 읽으며 결과 파일에 저장하지 않는다. 전송 오류는 예외 종류만 기록한다.

결과는 기본적으로 무시되는 `loadtest/results/`에 저장된다. `--output`으로 별도 경로를 정할 수 있다.
전체 요청 결과·단계 판정·워밍업·사전 로그인·잔액 검증은 JSON 원본으로 확인한다.
실패 단계 또는 준비 실패가 있으면 종료 코드는 1이다.

## 검증

```bash
.venv/bin/python -m unittest discover -s loadtest/tests -q
.venv/bin/ruff check loadtest/split_scenarios.py loadtest/tests/test_split_scenarios.py
```

공식 근거: [Locust HttpSession](https://docs.locust.io/en/stable/api.html#httpsession-class),
[라이브러리 방식 실행](https://docs.locust.io/en/stable/use-as-lib.html).

## 조사 문서의 설정을 현재 VM에 재현

WSL 제어 체크아웃에서 기존 인벤토리를 사용한다. VM 생성·DB 초기화·마이그레이션은 수행하지 않는다.

```bash
bash deploy/lab.sh performance
ansible-playbook -i deploy/lab/.runtime/inventory.json deploy/ansible/verify-performance.yml
ansible-playbook -i deploy/lab/.runtime/inventory.json deploy/ansible/loadtest-pool.yml
```

성능 설정은 API VM당 worker 4개, worker당 DB 풀 20+0(5초 대기), DB 최대 연결 250,
Nginx worker 연결 4096·파일 한도 8192·upstream keepalive 128이다.
`performance`는 로컬 백엔드의 엔진 설정 파일만 두 API에 전송하고 순서대로 재시작한다.
일반 배포는 드라이버의 TLS 동작을 유지한다. 문서의 **암호화 없는 실습 비교를 명시적으로 선택한 경우에만**
`bash deploy/lab.sh performance -e performance_disable_db_tls=true`를 사용한다.
기본 명령을 다시 실행하면 TLS 비활성 옵션은 false로 복원된다.

`loadtest-pool.yml`은 별도 시험 고객 10,000명(90% 3천만원, 10% 3만원)과 초기 원장만 직접 추가한다.
기존 고객·거래는 수정하거나 삭제하지 않는다. 초기 원장은 계정 준비이며 실제 입금 API 이벤트가 아니다.
기존 pool `.env`가 있으면 재삽입하지 않는다. 공용 시험 비밀번호를 쓰므로 실습 고객 전용이다.
자격 증명은 API와 제어 PC의 `.env`에만 저장된다. 맥북에서 실행할 때는 이 파일을 비공개로 가져와
`loadtest/pool/.env`에 보관하고 접근 권한을 600으로 제한한다. 버전 관리에 추가하지 않는다.

```bash
.venv/bin/python loadtest/split_scenarios.py transfer \
  --host http://172.30.1.191 --allow-remote \
  --pool-env loadtest/pool/.env --accounts 1000 --prelogin-rate 5 \
  --rates 80,160 --warmup 10 --seconds 60
```

계정 풀 재사용 시 가입·입금 호출은 없다. 전원 사전 로그인 후 조회한 현재 잔액을 기준으로 검증한다.
`--accounts`는 풀의 앞 N개를 선택한다. 계정이 이미 사용 중인 누락이 주원인일 때만 참여 수를 늘려 비교한다.
사전 로그인 자체가 실패하면 송금 측정은 시작하지 않는다. 서버 메모리 부족이 발생하면 그 실행을
송금 처리량 결과로 간주하지 않는다.

`missed_schedule_reasons.account_busy`와 `scheduler_late`는 서로 배타적이다.
두 조건이 겹치면 scheduler_late에 포함하고 `both`에도 별도로 기록한다.
따라서 앞 두 값의 합은 missed_schedule이며, both를 다시 합산하지 않는다.
`flow_duration_ms`는 잔액 조회부터 마지막 잔액 조회까지 실행된 흐름(조기 중단 포함)의 백분위,
`peak_inflight_flows`는 최대 동시 진행 흐름 수다. 일정 지연 백분위와 발생기 프로세스 CPU도 기록한다.
프로세스 CPU 100%는 한 코어를 뜻하며, 측정 시작부터 응답 대기 종료까지의 구간이다.
HTTP p95와 흐름 전체 p95를 구분해야 한다.

다중 worker의 현재 /metrics는 응답한 worker의 값이므로 모든 worker의 요청 합계가 아니다.
성능 판정은 외부 실행기의 통계를 기준으로 한다. 원본 문서의 APM·Tempo·py-spy 계측은
현재 저장소로 이식하지 않았으므로 원본과 동일한 계측 조건의 실험이라고 주장하지 않는다.

사전 로그인은 `--prelogin-concurrency`(기본 8)로 진행 중인 로그인 수를 제한한다.
초당 로그인 예약 수와 동시 로그인 수는 다르다. 목표 20건/초여도 서버가 늦으면 준비 속도를 낮추며,
모든 사전 로그인이 끝나야 측정한다. 이는 메모리가 큰 비밀번호 검증의 대기가 무한히 누적되는 것을 막는다.
manifest의 실제 준비 시간·성공 인원·동시 한도를 함께 확인한다.
