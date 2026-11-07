# 송금 부하시험 및 병목 추적 정리

> 이 문서의 1~10장은 사용자가 제공한 다른 환경의 과거 조사 기록입니다.
> 현재 배포는 SSH `172.30.1.92`, VM `172.30.1.191~200`입니다.
> 원본 환경의 APM·Tempo·py-spy 소스는 이 저장소에 없으며, 해당 계측을 이식했다고 간주하지 않습니다.
> 이번 작업에서 재현한 설정과 실제 재시험 결과는 마지막 장을 기준으로 확인하세요.


- 작업 기간: 2026-11-07~2026-11-08, 한국시간(KST)
- 정리 시점: 2026-11-08, DB 연결 한도 250개 적용 후 160건/초 재시험까지
- 저장소: `mlo-03-p1-team3`
- 결과 JSON의 시각 및 `20261107T...Z` 디렉터리명은 UTC다. 한국시간으로는 다음 날인 실행도 있다. 결과 상위 폴더의 날짜 표기보다 manifest의 시각을 우선한다.

## 1. 현재 결론

1. **80건/초는 통과했다.** DB TLS 해제 후 전체 HTTP 요청 p95가 2,800ms에서 180ms로 줄었고 실패는 0건이었다.
2. **160건/초는 아직 통과하지 못했다.** 최종 구성에서 HTTP 실패는 0건이나 실제 송금 시도는 110.2건/초, 전체 요청 p95는 2,400ms다.
3. nginx 연결·파일 제한, DB TLS 연결 초기화, DB 최대 연결 수 문제를 각각 확인했다. 각각 해소해도 API 처리 대기는 일부 남았다.
4. **DB 연결 미반납은 이번 계측에서 관측되지 않았다.** 부하 종료 후 네 worker 모두 대여·반납 수가 같았고 현재 대여는 0개였다. 풀에 보관된 유휴 연결 78개는 DB의 `Sleep` 연결 78개와 일치했다.
5. 최종 160건/초 시험은 예정 흐름 9,600개 중 2,988개를 시작하지 못했다. 따라서 110.2를 서버의 확정 최대 처리량으로 해석하면 안 된다.

## 2. 환경과 계정 준비

- WSL 접속: `ssh playdata@192.168.1.253`
- WSL 배포 체크아웃: `/home/playdata/podobank_rust`
- API 입구: `http://192.168.1.191` → nginx → HAProxy → API VM 두 대
- API VM당 사양: 4 vCPU, 약 2GB 메모리
- Python 3.14.10, FastAPI 0.162.0, Uvicorn 0.54.0, SQLAlchemy 2.1.6, PyMySQL 1.2.3
- DB: MariaDB primary/replica, 이벤트 저장 MongoDB
- 관측: Prometheus, Grafana, Loki, Alloy, OpenTelemetry, Tempo, py-spy
- 시험 회원 10,000명을 DB에 직접 준비했다. 가입·입금 API를 부하 준비 시나리오로 실행하지 않는다.
- 초기 자금: 9,000명은 각 30,000,000원, 1,000명은 각 30,000원. 총 270,030,000,000원.
- 송금 시험 참여 계정은 기존 풀 중 1,000개다. 계정 비밀번호는 전용 `loadtest/pool/.env`에만 보관한다.
- 직원 계정은 별도로 1개이며 고객 계정 10,000개와 구분한다.

## 3. 시험 방식과 지표 해석

- 한 흐름: 잔액 조회 → 받는 사람 확인 → 송금 → 잔액 조회.
- 목표 160은 **송금 흐름 시작 160개/초**다. 정상 전달 시 HTTP 요청은 약 640개/초다.
- 표의 `송금 시도/초`는 스크립트의 `transfer_attempts / seconds`다. 성공적으로 완료된 금융 거래 수와 같다고 단정할 수 없다. 예상된 잔액 부족 응답도 별도 집계된다.
- p95는 **전체 HTTP 요청** 기준이며 송금 API만의 지연이나 흐름 전체 소요 시간이 아니다.
- 기본 측정: 워밍업 10초, 본 측정 60초. 사전 로그인은 최초 일부 시험에서 5개/초, 이후 20개/초다. 모두 로그인한 뒤에만 송금 측정을 시작한다.
- 같은 계정으로 동시에 송금하지 않는다. 예정 시각을 크게 놓치거나 계정이 이미 사용 중이면 `missed_schedule`을 증가시키고 건너뛴다.
- 현재 `missed_schedule`은 위 두 사유를 분리하지 않는다. 미전달 부하를 모두 서버 오류나 부하 발생기 CPU 문제로 해석하지 않는다.
- 실패율, 지연(p95 500ms), 일정 미전달, 목표 송금 시도율 미달 등으로 판정한다. 실패 단계 이후 더 높은 단계는 실행하지 않는다.
- 응답이 불확실한 송금에 관련된 계좌는 개별 예상잔액 검증에서 제외하고 `uncertain`으로 남긴다. DB 전체 잔액·원장 일치 확인과는 별도 검증이다.

## 4. 현재 적용된 설정

아래 worker·풀·nginx·DB 한도·계측 비활성 상태는 문서 작성 중 원격 조회로 재확인했다.

| 항목 | 최종 상태 |
|---|---|
| API worker | VM당 4개, 전체 8개 |
| DB 풀 | worker당 `pool_size=20`, `max_overflow=0`, 대기 제한 5초 |
| API 전체 이론상 DB 연결 상한 | 8 × 20 = 160개. exporter·운영·수집 연결은 별도 |
| MariaDB `max_connections` | 250개 |
| API→MariaDB TLS | 해제 상태. DB 연결에서 비활성 검증 완료 |
| nginx `worker_connections` | 4096 |
| nginx `worker_rlimit_nofile` | 8192 |
| nginx upstream keepalive | 128 |
| 백엔드 HTTP | HTTP/1.1, `Connection` 헤더 제거, 연결 재사용 |
| HAProxy 상태 점검 | 기존 설정 유지. 실측에서 2초 응답 지연으로 DOWN 발생 |
| OpenTelemetry | 기본 10% 표본 수집, 요청·SQL·DB 획득·스레드 대기·이벤트 저장 계측 |
| Tempo | 2.10.10, Loki VM에 설치, 로컬 저장, 보관 24시간 |
| 풀 대여·반납 진단 | `POOL_OBSERVE_ENABLED=false`, 측정 종료 후 비활성화 |
| 임시 Uvicorn transport 실행기 | 해제. 원래 Uvicorn 실행 명령으로 복구 완료 |

TLS는 실습 비교를 위해 해제한 상태이며 API→DB 통신은 암호화되지 않는다. 원래 접속 설정은 VM의 비공개 `.env` 백업에 보관했다. 비밀값이나 접속 문자열 원문은 이 문서에 기록하지 않는다.

VM 설정과 저장소 기본 설치 흐름이 모두 동일한 것은 아니다. worker는 systemd drop-in, DB 한도는 별도 설정 파일, TLS 옵션은 비공개 API 환경 파일에 적용돼 있다. 전체 재배포 전에 현재 설정 유지 여부를 확인해야 한다. `deploy/ansible/site.yml`은 DB 초기화 단계를 포함하므로 재시험을 위해 실행하지 않는다.

## 5. 주요 송금 시험 결과

각 링크의 manifest가 원본 근거다. 변경이 누적됐고 프로파일러·계측 여부도 다르므로 모든 행을 엄밀한 단일 변수 반복 실험으로 취급하지 않는다.

| 시험 구성/변경 | 목표 흐름/초 | 송금 시도/초 | HTTP 실패 | p95(ms) | 일정 누락 | 판정 |
|---|---:|---:|---:|---:|---:|---|
| [초기 설정](../loadtest/results/transfer-dbseed-20261107/20261107T132651Z-transfer/manifest.json) | 10 | 10.00 | 0 | 15 | 0 | 통과 |
| [초기 설정](../loadtest/results/transfer-dbseed-20261107/20261107T132651Z-transfer/manifest.json) | 20 | 20.00 | 0 | 15 | 0 | 통과 |
| [초기 설정](../loadtest/results/transfer-dbseed-20261107/20261107T132651Z-transfer/manifest.json) | 40 | 40.00 | 0 | 20 | 0 | 통과 |
| [초기 설정](../loadtest/results/transfer-dbseed-20261107/20261107T132651Z-transfer/manifest.json) | 80 | 73.00 | 1,078 | 1,500 | 0 | 실패 |
| [nginx 연결 4096, 파일 제한 1024](../loadtest/results/transfer-nginx4096-20261107/20261107T134320Z-transfer/manifest.json) | 80 | 51.35 | 1,628 | 9,400 | 180 | 실패 |
| [파일 제한 8192 보완](../loadtest/results/transfer-nginx4096-fd8192-20261107/20261107T135118Z-transfer/manifest.json) | 80 | 69.10 | 52 | 5,000 | 635 | 실패 |
| [APM 적용, worker 1](../loadtest/results/transfer-apm-20261107/20261107T141427Z-transfer/manifest.json) | 80 | 60.05 | 1,241 | 4,900 | 599 | 실패 |
| [worker 2](../loadtest/results/worker2-20261107/20261107T144539Z-transfer/manifest.json) | 80 | 80.00 | 0 | 2,400 | 0 | 실패 |
| [worker 2, 호스트·스케줄러 관측](../loadtest/results/evidence-a-20261107/20261107T145308Z-transfer/manifest.json) | 80 | 80.00 | 0 | 2,300 | 0 | 실패 |
| [HTTP 연결 재사용](../loadtest/results/reuse-20261107/20261107T145922Z-transfer/manifest.json) | 80 | 80.00 | 0 | 2,800 | 0 | 실패 |
| [호출 스택 프로파일링 동시 실행](../loadtest/results/profile-20261108/20261107T150358Z-transfer/manifest.json) | 80 | 71.75 | 20 | 4,500 | 488 | 실패 |
| [DB TLS 해제](../loadtest/results/db-tls-off-20261108/20261107T151306Z-transfer/manifest.json) | 80 | 80.00 | 0 | 180 | 0 | 통과 |
| [풀 20+0](../loadtest/results/pool20-20261108/20261107T151921Z-transfer/manifest.json) | 80 | 80.00 | 0 | 180 | 0 | 통과 |
| [worker 2, 160건/초](../loadtest/results/transfer160-20261108/20261107T152345Z-transfer/manifest.json) | 160 | 86.57 | 4,086 | 2,900 | 2,453 | 실패 |
| [worker 4, DB 한도 151](../loadtest/results/workers4-160-20261108/20261107T152842Z-transfer/manifest.json) | 160 | 109.98 | 121 | 2,400 | 2,937 | 실패 |
| [worker 2 복구, 대여·반납 계측](../loadtest/results/pool-observe-20261108/20261107T153517Z-transfer/manifest.json) | 160 | 85.93 | 2,979 | 3,100 | 2,848 | 실패 |
| [worker 4 재시험, DB 한도 151](../loadtest/results/workers4-repeat-20261108/20261107T154013Z-transfer/manifest.json) | 160 | 107.05 | 308 | 2,700 | 3,005 | 실패 |
| [worker 4, DB 한도 250](../loadtest/results/db250-workers4-20261108/20261107T154422Z-transfer/manifest.json) | 160 | 110.20 | 0 | 2,400 | 2,988 | 실패 |

별도 로그인 시험은 1·2·5·10·20건/초 모두 실패 0건, p95 66~78ms로 통과했다. 최대 로그인 처리량을 찾은 결과는 아니다.

- [로그인 결과](../loadtest/results/login-dbseed-20261107/20261107T130756Z-login/manifest.json)
- 최종 160건/초: HTTP 요청 26,448건, 송금 시도 6,612건, 일정 누락 2,988건, 완료되지 않은 흐름 0개.
- 최종 DB 한도 초과 누적 카운터는 시험 전후 344건으로 동일했다. 새 연결 한도 오류는 없었다.
- 최종 측정 구간에 HAProxy의 API DOWN 기록이 없었다.

## 6. 원인별 근거

### 6.1 nginx 연결 슬롯과 파일 제한

최초 80건/초에서 연결 초기화·끊김 1,078건이 발생했다. 연결 슬롯만 768→4096으로 늘렸을 때는 `socket() failed (24: Too many open files)`가 발생했다. 실제 worker의 파일 열기 soft limit은 1024개였다. systemd의 높은 한도만 보고 충분하다고 판단했던 초기 확인은 불충분했다.

`worker_rlimit_nofile=8192`까지 반영한 뒤 해당 연결 오류와 nginx 500은 사라졌으나 API 지연과 HAProxy 503이 남았다.

이번 시험보다 앞선 시각의 `768 worker_connections are not enough` 로그는 발견했지만, 이를 이번 실행의 직접 원인 증거로 사용하지 않았다.

### 6.2 요청이 앱에 들어오기 전의 연결 수락 대기

HAProxy 응답의 `X-Trace-ID`와 백엔드 연결 포트, API VM 패킷 시각, APM 시각을 같은 요청으로 연결했다.

진단용 실행기로 129개 요청을 연결한 표본의 p95:

| 구간 | p95 |
|---|---:|
| API VM에 요청 데이터 도착 → Uvicorn 연결 수락 콜백 | 2,153ms |
| 연결 수락 → 데이터 읽기 | 6.1ms |
| 데이터 읽기 → HTTP 헤더 처리 | 0.115ms |
| 헤더 처리 → 앱 작업 실행 | 12.483ms |
| 앱 작업 실행 → APM 시작 | 0.450ms |
| APM 앱 내부 처리 | 312.881ms |

이는 연결 수락 콜백 전 지연을 확인한 결과다. 커널의 accept 시스템 호출과 런타임 콜백 사이까지 완전히 분해한 결과는 아니다. 같은 VM 안의 시각 비교를 우선했고, VM 간 시계 차이가 수 ms 있음을 확인했다. 패킷 수집기의 커널 드롭은 0건이었다.

- [요청별 상관 분석](../loadtest/results/correlation-v2-20261107/20261107T143514Z-transfer/correlation.json)
- [연결 대기열 요약](../loadtest/results/correlation-v2-20261107/20261107T143514Z-transfer/queue-summary.json)

### 6.3 HTTP 연결 재사용

nginx upstream keepalive, HTTP/1.1, `Connection` 헤더 제거를 적용했다.

80건/초 비교에서 HAProxy 새 백엔드 연결은 약 303→47개/초, API 연결 수락 대기열 평균은 123·112→18·25개로 줄었다. 그러나 p95는 2.3→2.8초로 개선되지 않았다. 연결 생성 부담을 줄였지만 전체 지연의 유일한 원인은 아니었다. 한 번의 비교에서 0.5초 차이가 설정 때문에 발생했다고 확정할 수 없다.

같은 IP·포트 조합이 여러 요청에 나타나는 것만으로 연결 재사용률을 계산하지 않는다. 포트 재사용일 수도 있다.

- [적용 전 자원 기록](../loadtest/results/evidence-a-20261107/20261107T145308Z-transfer/evidence-summary.json)
- [적용 후 자원 기록](../loadtest/results/reuse-20261107/20261107T145922Z-transfer/evidence-summary.json)

### 6.4 DB TLS 초기화와 연결 생성

py-spy 스택에서 `SSLContext.load_default_certs`, PyMySQL 새 연결 생성, TLS 소켓 읽기·쓰기가 확인됐다. PyMySQL 1.2.3의 설치된 코드에서 별도 SSL 옵션이 없어도 TLS PREFERRED 모드로 시도하는 동작을 확인했다.

읽기 전용 연결 비교 결과:

| 조건 | 새 연결 생성 중앙값: 순차 | 새 연결 생성 중앙값: 동시 8개 | 기존 연결 SELECT 1 p95: 동시 8개 |
|---|---:|---:|---:|
| TLS 해제 | 1.132ms | 3.914ms | 1.947ms |
| TLS 컨텍스트 재사용 | 7.752ms | 22.445ms | 2.208ms |
| 기본 TLS 컨텍스트 매번 생성 | 20.248ms | 90.033ms | 1.869ms |

TLS 컨텍스트 생성만의 중앙값은 12.327ms였다. 단순 SELECT의 암호화 통신보다 새 연결의 초기화 비용에서 큰 차이가 났다. 시험 순서는 고정돼 있었으며 이 수치를 운영 환경의 보장값으로 사용하지 않는다.

실제 송금 시험에서 DB TLS만 해제한 뒤 80건/초 p95는 2,800→180ms, 실패는 0건, API DOWN 기록은 없음으로 바뀌었다. 강한 비교 근거지만 수초 지연의 모든 메커니즘을 입증한 것은 아니다.

- [TLS 분리 시험](../loadtest/results/tls-isolation-20261108/podobank-tls-isolate.json)
- [풀 반복 접속 시험](../loadtest/results/tls-isolation-20261108/podobank-pool-probe.json)
- [TLS 해제 송금 시험](../loadtest/results/db-tls-off-20261108/20261107T151306Z-transfer/manifest.json)

### 6.5 DB 풀의 반납과 연결 유지

`with engine.connect()`와 `with engine.begin()`을 빠져나가면 연결을 풀에 반납한다. 반납은 연결 종료와 다르다. 풀에 보관된 연결은 DB에서 보통 `Sleep`으로 남으며 DB 연결 한도에 포함된다.

초기 풀 10+10 설정의 읽기 전용 반복 접속 시험에서 연결 획득 80회 동안 실제 연결 50개 생성·40개 종료가 관측됐다. 풀 20+0으로 변경해 추가 연결 종료·재생성 경로를 줄였다. TLS 해제 상태의 80건/초 p95는 변경 전후 모두 180ms였다.

worker 2개 × VM 2대에서 대여·반납 이벤트를 계측한 최종 상태:

| worker PID(당시) | 누적 대여 | 누적 반납 | 현재 대여 | 풀 유휴 연결 |
|---|---:|---:|---:|---:|
| API-1 / 645336 | 14,527 | 14,527 | 0 | 20 |
| API-1 / 645337 | 14,278 | 14,278 | 0 | 20 |
| API-2 / 644933 | 13,332 | 13,332 | 0 | 18 |
| API-2 / 644934 | 13,701 | 13,701 | 0 | 20 |

합계 대여·반납은 각각 55,838회다. 풀 유휴 연결 78개와 DB `Sleep` 78개가 일치했다. 관측 기간 worker별 최대 대여는 15~18개로 20개 한도에 도달하지 않았다. 해당 실행에서 연결 누수나 풀 고갈은 관측되지 않았다는 뜻이며 모든 상황의 누수 부재를 증명하지는 않는다.

- [대여·반납 계측](../loadtest/results/pool-observe-20261108/20261107T153517Z-transfer/pool-summary.txt)

### 6.6 worker 증설과 DB 한도

worker 4개 × VM 2대 × 풀 20개 = API에서 최대 160개 연결을 보관할 수 있다. 기존 DB 한도 151개를 넘으므로 연결을 정상 반납해도 `Too many connections`가 발생할 수 있다.

실제 worker 4개 시험에서 DB 최대 사용 연결 152개와 `1040 - Too many connections`를 확인했다. 관리자용 예약 연결 때문에 표시가 설정값보다 하나 클 수 있으며 이를 일반 API의 추가 여유로 계산하지 않는다. 실패 응답은 API의 `database_unavailable`이었다.

DB 한도를 250개로 올린 후 연결 거절과 HTTP 오류는 사라졌다. 그러나 실제 송금 시도는 110.2건/초, p95 2.4초로 남았다. DB 연결 한도 문제와 API 처리 지연은 구분해야 한다.

### 6.7 CPU·작업 대기와 관측 한계

- worker 2개, TLS 해제 전 80건/초 기록에서 Windows CPU 평균 59%, 최대 71%, 호스트 실행 대기열 최대 1개였다. 호스트 전체 포화라는 증거는 약했다.
- 같은 시기 API 게스트 CPU 압력 평균 약 29%, 주 스레드 실행 대기 약 8.5~8.7%가 관측됐다.
- TLS 해제 후 160건/초 worker 2개 시험: 연결 수락 대기열 최대 442·457개, 스레드 대기 p95 163ms, DB 획득 p95 19ms, SQL p95 15ms, 앱 송금 요청 p95 약 1.09초였다.
- worker 4개·DB 한도 151개 시험에서는 주 스레드 실행 대기 약 22%, 게스트 CPU 압력 약 62%로 증가했다. 이 실행은 DB 연결 거절도 겹쳤으므로 순수한 worker 효율 비교로 볼 수 없다.
- 게스트 `%steal=0`만으로 VMware 호스트의 CPU 경쟁을 배제하지 않는다.
- py-spy 일반 스레드 표본에는 대기 중인 스레드가 포함될 수 있다. 표본 개수를 CPU 점유율로 해석하지 않는다. 프로파일러를 켠 실행은 성능 비교에 별도 표시한다.
- 다중 worker에서 현재 `/metrics`는 요청을 받은 프로세스의 지표를 반환한다. 전체 worker의 합계·최대치로 해석하지 않는다. 풀 대여·반납은 PID별 로그로 따로 측정했다.

## 7. 최종 검증과 한계

- 최신 단위 테스트: `/tmp/podobank-apm-venv/bin/pytest tests/unit -q` → **205 passed**, 종료 코드 0. TestClient의 httpx 관련 경고 1개가 있었다.
- 수정 계측 코드 린트: `ruff check` → `All checks passed!`.
- `git diff --check` → 오류 없음.
- 최종 부하시험: 종료 코드 **1**. HTTP 오류는 없지만 p95·목표 부하 전달 기준 실패다.
- 최종 개별 잔액 검증: 1,000개 확인, 불확실 0개, 불일치 0개, 조회 오류 0개.
- 최종 DB 조회: 계좌 10,000개, 총잔액 270,030,000,000원, 계좌 잔액과 원장 합계 불일치 0건.
- 시험 후 `/api/v1/health`: HTTP 200.
- 이전 실패 실행의 `uncertain` 계좌를 모두 개별 재구성한 것은 아니다. 전체 잔액·원장 일치가 모든 거래의 중복·유실 부재를 입증하는 것은 아니다.
- 파괴적인 전체 통합 테스트를 운영 실습 DB에 실행하지 않았다.
- 재부팅 후 영속성은 아직 시험하지 않았다. DB 설정 파일과 런타임 값의 적용만 확인했다.

## 8. 주요 수정 파일과 VM 적용 위치

| 목적 | 저장소 / VM 경로 |
|---|---|
| 시험 계정 재사용 | `loadtest/account_pool.py`, `loadtest/split_scenarios.py`, 관련 테스트·예시 환경 파일 |
| APM | `backend/app/observability/tracing.py`, 요청·로그·metrics·인증·금융·이벤트 계측, `backend/requirements.txt` |
| 풀 대여·반납 | `backend/app/observability/pool_observer.py`, `backend/tests/unit/test_pool_observer.py` |
| 진단용 transport | `backend/app/observability/trace_server.py`, `deploy/ansible/trace-transport.yml`（현재 비활성） |
| Tempo / Grafana | `deploy/ansible/tracing.yml`, `templates/tempo.yml.j2`, `verify-tracing.py` |
| worker | `deploy/ansible/api-workers.yml` → `/etc/systemd/system/podobank-api.service.d/workers.conf` |
| HTTP 재사용 | `deploy/ansible/proxy-reuse.yml` → `/etc/nginx/conf.d/podobank.conf` |
| HAProxy 상관 로그 | `deploy/ansible/trace-proxy.yml` → `/etc/haproxy/haproxy.cfg` |
| DB 풀 | `backend/app/core/config.py` → `/opt/podobank/backend/app/core/config.py` |
| DB 한도 | `deploy/ansible/mariadb-connections.yml` → `/etc/mysql/mariadb.conf.d/99-podobank-connections.cnf` |
| nginx 한도 | VM `/etc/nginx/nginx.conf` |
| API 접속·관측 환경 | VM `/etc/podobank/api.env`（비공개） |

추가 의존성: OpenTelemetry SDK·OTLP HTTP exporter 1.45.2, FastAPI instrumentor 0.66b2는 요청 추적용이며, py-spy 0.4.3은 호출 스택 진단용이다. 모두 requirements에 버전을 기록했다. py-spy는 VM의 별도 `/opt/podobank-profile` 경로에 설치했다. SQLAlchemy 자동 계측 패키지는 2.1 지원 범위 문제로 제거하고 공개 실행 이벤트로 직접 계측했다.

이번 작업에서는 커밋·푸시하지 않았다. 기존 사용자 변경과 진단 변경이 작업 트리에 함께 있으므로 커밋 전 범위를 검토한다. 결과 폴더가 ignore될 수 있으므로 문서 링크만 커밋하면 원본 결과가 함께 전달된다고 가정하지 않는다. `.env`를 강제 추가하지 않는다.

## 9. 다음 재개 순서

아래는 제안이며 아직 실행하지 않았다.

1. **일정 누락 사유를 분리한다.** `missed_schedule`을 `account_busy`와 `scheduler_late`로 나눠 각각 기록한다. 현재 2,988개 누락의 직접 사유는 확인하지 못했다.
2. 같은 설정에서 경로별 지연·흐름 전체 소요 시간·동시 진행 흐름 수·부하 발생기 CPU와 일정 지연을 함께 수집한다.
3. 계정이 사용 중인 것이 주원인이면 기존 10,000개 풀 중 참여 수만 늘려 비교한다. 서버 설정은 동시에 바꾸지 않는다.
4. 발생기 일정 지연이 주원인이면 발생기 실행 여유를 확보한 뒤 동일 부하를 다시 전달한다.
5. 목표 160건/초를 온전히 전달하는 조건을 먼저 확보한 뒤 API worker·스레드 대기·GIL·스케줄링을 요청별로 분석한다.
6. APM은 10% 표본과 쿼리 결과 제한 때문에 특정 시점의 일부 요청을 본다. 느린 요청 표본과 전체 성능을 구분하고, 필요하면 같은 조건의 계측 켬·끔 비교를 한다.
7. TLS를 복원하려면 컨텍스트 재사용과 안정적인 풀 유지 상태에서 별도로 비교한다. TLS 해제 상태를 일반 배포의 기본값으로 간주하지 않는다.

### 동일 조건 재실행 명령

로컬 저장소 루트에서 실행한다. 현재 환경에 존재하는 인터프리터 경로이므로 다른 PC에서는 해당 가상환경 경로를 확인한다.

```bash
/Users/ckh/repos/podobank_rust/lab/.venv/bin/python loadtest/split_scenarios.py transfer \
  --host http://192.168.1.191 --allow-remote \
  --accounts 1000 --pool-env loadtest/pool/.env \
  --prelogin-rate 20 --rates 160 --warmup 10 --seconds 60 \
  --output loadtest/results/db250-workers4-20261108
```

이 명령은 실제 실습 DB에 송금과 이벤트를 추가한다. 가입·입금은 생략하며 결과는 새 UTC 시각 하위 폴더에 저장된다.

### APM 조회

- Grafana: `http://192.168.1.200:3000/explore`, 데이터 소스 `Tempo` / UID `podobank-tempo`
- 서비스: `podobank-api`, 인스턴스: `api-1`, `api-2`
- 검증용 실제 송금 trace ID: (원본 비공개 기록 참조)
- 추적 구간: `auth.resolve_session`, `db.acquire`, `db.query`, `db.transaction`, `money.execute`, `events.file_write`, `events.mongodb_insert`, `threadpool.wait`
- Tempo 보관이 24시간이므로 위 trace ID는 이후 만료될 수 있다. 로컬 분석 JSON은 별도 보관한다.

## 10. 참고한 공식 자료

- [nginx upstream keepalive](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#keepalive)
- [nginx worker_connections / worker_rlimit_nofile](https://nginx.org/en/docs/ngx_core_module.html)
- [HAProxy 2.8 로그·타이밍·연결 재사용](https://docs.haproxy.org/2.8/configuration.html)
- [SQLAlchemy 연결 풀](https://docs.sqlalchemy.org/en/21/core/pooling.html)
- [SQLAlchemy SQL 실행 시간 이벤트](https://docs.sqlalchemy.org/en/21/faq/performance.html)
- [FastAPI 동기 함수와 스레드 풀](https://fastapi.tiangolo.com/async/)
- [Uvicorn 설정](https://uvicorn.dev/settings/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
- [Tempo](https://grafana.com/docs/tempo/latest/)
- [PyMySQL 변경 기록](https://github.com/PyMySQL/PyMySQL/blob/main/CHANGELOG.md)
- [py-spy 0.4.3](https://github.com/benfred/py-spy/releases/tag/v0.4.3)
- [Linux CPU 압력(PSI)](https://docs.kernel.org/accounting/psi.html)
- [Linux 스케줄러 통계](https://docs.kernel.org/scheduler/sched-stats.html)
- [AWS EC2 네트워크 한도 지표](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/monitoring-network-performance-ena.html)

EC2 AMI만으로 FastAPI 성능을 판단할 수 없다. 인스턴스 종류·CPU 구조·네트워크 드라이버·worker 수·요청 내용이 함께 필요하다. 현재 환경은 VMware이므로 EC2의 CPU 크레딧·ENA 한도 지표를 그대로 적용하지 않았다. 우리 송금 시험과 직접 비교 가능한 EC2 벤치마크는 확인하지 못했다.

## 11. 현재 VM 재현 및 재시험 — 2026-11-08 KST

이 장은 앞선 다른 환경의 결과와 구분한 **이번 실행 기록**이다. SSH는 `172.30.1.92`, VM은 `172.30.1.191~200`을 사용했다.
기존 DB는 초기화하지 않고 전용 고객 10,000명과 초기 원장만 추가했다. 기존 계정·거래·로그는 삭제하지 않았다.
원본 APM·Tempo·py-spy 코드는 없는 상태이며 이번에 새로 구성하지 않았다. 따라서 원본과 동일한 계측 조건의 단일 변수 비교가 아니다.

### 적용 및 검증

- `deploy/ansible/performance.yml`: DB 250 연결(온라인 적용+설정 파일), Nginx 4096 연결·8192 worker 파일 한도·keepalive 128, API당 worker 4개·풀 20+0·대기 5초.
- API 2대는 순서대로 재시작했고 실제 worker 4개씩을 확인했다. API→DB TLS 비활성은 실습 명령에서만 선택했다. 원래 접속 문자열은 바꾸지 않았으며 기본 배포는 TLS 비활성을 강제하지 않는다.
- 같은 Ansible 설정을 두 번째 실행했을 때 5개 대상 모두 `changed=0 unreachable=0 failed=0`이었다.
- `verify-performance.yml`은 실 DB 연결의 TLS 상태·풀·DB 연결 한도와 Nginx worker의 실제 파일 한도를 확인한다.
- `loadtest-pool.yml`은 별도 고객 준비를 자동화한다. 자격 증명은 비공개 `.env`로만 전달되며 커밋하지 않는다.
- `split_scenarios.py`는 계정 재사용·시작 잔액 조회, 일정 누락 사유 분리, 흐름 소요 시간·동시 진행 수·발생기 CPU를 기록한다.

### 결과

오류율 1% 이하, **전체 HTTP 요청 p95 500ms 이하**, 목표 전달·일정 누락·인증 분리 조건으로 판정했다. 예상된 잔액 부족 409는 별도 정상 시나리오로 취급한다.
송금 흐름은 잔액→받는 사람→송금→잔액이며 실제 송금 시도와 금융 성공 건수를 구분한다.

| 모드 | 계정 | 목표/초 | 실제 송금 시도/초 | HTTP 요청 | HTTP 실패 | HTTP p95 ms | 누락(계정/일정) | 판정 |
|---|---:|---:|---:|---:|---:|---:|---|---|
| login | 1000 | 20 | 0.00 | 1,200 | 0 | 250 | 0/0 | 통과 |
| transfer | 1000 | 80 | 80.00 | 19,200 | 0 | 44 | 0/0 | 통과 |
| transfer | 1000 | 160 | 133.12 | 31,948 | 0 | 1900 | 1613/0 | 기준 미달 |
| transfer | 3000 | 160 | 137.42 | 33,952 | 1,308 | 7600 | 755/44 | 기준 미달 |

초기 사전 로그인 20건/초(동시 수 제한 없는 실행)는 1,000명 중 678명 성공 후 중단했다. HTTP 502 320건과 전송 오류 2건이었다. 두 API VM의 커널 OOM 로그에서 Python 프로세스 강제 종료를 확인했다. **송금 단계는 0개이므로 이 결과는 송금 실패가 아니다.**
첫 로그인 전용 20건/초 통과와 별도 사전 로그인 실패를 혼동하지 않는다. 종료 후 서비스가 복구됐으며, 이후 시험에서는 사전 로그인 완료를 다시 확인했다.
1,000명 재시험은 사전 로그인 5건/초, 3,000명 비교는 사전 로그인 20건/초·동시 최대 8개로 준비했다. 준비 부하는 측정 구간에서 제외했다.
1,000명·160건/초의 누락 1,613개는 모두 account_busy였고 scheduler_late는 0이었다. 계정 수를 늘리는 비교 중 서버 설정은 변경하지 않았다.
배타적인 account_busy+scheduler_late 합이 missed_schedule이며 both는 두 조건의 겹침 표시이므로 다시 합산하지 않는다.

| 계정·송금 목표 | 흐름 전체 p95 ms | 최대 진행 흐름 | 일정 지연 p95 ms | 발생기 CPU(1코어=100%) |
|---|---:|---:|---:|---:|
| 1000·80 | 138.8 | 20 | 1.35 | 25.7% |
| 1000·160 | 7010.6 | 990 | 1.44 | 32.9% |
| 3000·160 | 21541.9 | 2049 | 1.51 | 35.1% |

흐름 전체 p95는 HTTP 요청 p95와 다른 값이다. 흐름에는 조기 중단된 실행도 포함한다. 응답 종료까지 기다린 뒤 통계를 고정하므로 측정 종료 후 완료된 요청도 해당 시작 구간에 포함된다.
발생기 CPU는 측정 시작부터 응답 대기 종료까지의 프로세스 CPU다. 서버 CPU는 Prometheus의 1분 idle rate 기반 5초 간격 표본으로 보고, 표본 최대를 순간 최대라고 단정하지 않는다.

### 금융 데이터 및 서비스 검증

- retry-results·1000명: 종료 잔액 {"checked": 1000, "uncertain": 0, "mismatched": 0, "errors": 0, "total_diff": 0}
- expanded-results·3000명: 종료 잔액 {"checked": 2281, "uncertain": 719, "mismatched": 0, "errors": 0, "total_diff": 0}
- accounts (master/replica): 16000, 16000
- ledger_entries (master/replica): 118324, 118324
- total_balance (master/replica): 405013109500, 405013109500
- balance_mismatches (master/replica): 0, 0
- invalid_transfer_pairs (master/replica): 0, 0
- negative_balances (master/replica): 0, 0

### 실행 명령 및 소스 검증

```bash
bash deploy/lab.sh performance -e performance_disable_db_tls=true
ansible-playbook -i deploy/lab/.runtime/inventory.json deploy/ansible/verify-performance.yml -e performance_assert_tls=true -e performance_disable_db_tls=true
ansible-playbook -i deploy/lab/.runtime/inventory.json deploy/ansible/loadtest-pool.yml
.venv/bin/python loadtest/split_scenarios.py login --host http://172.30.1.191 --allow-remote --accounts 1000 --pool-env loadtest/pool/.env --rates 20 --warmup 10 --seconds 60
.venv/bin/python loadtest/split_scenarios.py transfer --host http://172.30.1.191 --allow-remote --accounts 1000 --pool-env loadtest/pool/.env --rates 80,160 --prelogin-rate 5 --warmup 10 --seconds 60
.venv/bin/python loadtest/split_scenarios.py transfer --host http://172.30.1.191 --allow-remote --accounts 3000 --pool-env loadtest/pool/.env --rates 160 --prelogin-rate 20 --prelogin-concurrency 8 --warmup 10 --seconds 60
.venv/bin/pytest backend/tests/unit deploy/tests -q
.venv/bin/python -m unittest discover -s loadtest/tests -q
```

- pytest: **215 passed, 4 subtests passed**, 기존 TestClient deprecation warning 1개.
- unittest: **15 tests OK**. 제한된 로그인 동시성, 일정 지연/계정 사용 중 분리, 인증과 송금 분리, 불확실 송금의 재시도 금지를 검증했다.
- 변경 Python 파일 `ruff check`: 통과. `git diff --check`: 통과.
- 최초 임시 계정 준비 playbook은 마지막 제어 PC 파일 권한 작업에서 불필요한 sudo 때문에 실패했다. 계정 준비 자체는 완료됐고 재삽입하지 않았다. 저장소 playbook에서 제어 PC 작업에 become=false를 지정해 수정·검증했다.
- 단위 테스트의 통과와 부하 기준 통과는 별개다. 실패한 부하시험을 통과했다고 기록하지 않는다.

### 원본 자료와 남은 한계

- 공유 가능한 수치 원본: [이번 재시험 JSON](loadtest/records/investigation-retest-20261108.json). 원본 환경의 상대 링크 파일이 이 저장소에 있다고 가정하지 않는다.
- 상세 산출물: 맥북 Downloads/podobank-investigation-retest-20261108. manifest·관측 JSONL·서버 확인 로그 보관. 비밀값과 쿠키는 결과에 저장하지 않았다.
- 다중 worker의 현재 /metrics는 응답한 프로세스의 지표다. 전체 요청 수는 외부 실행기 통계를 사용하며 현재 Grafana FastAPI counter를 전체 worker의 정확한 합계로 해석하지 않는다.
- TLS를 끈 실습 상태다. 운영 배포의 기본으로 취급하지 않으며 TLS 컨텍스트 재사용 비교는 수행하지 않았다.
- 재부팅 영속성·GIL/스레드 대기·원본 APM에 따른 요청별 상관 분석은 이번에 검증하지 않았다.
- 한정된 60초 송금 시험이며 실제 금융 업무 전체·장시간 안정성·서버 절대 최대 처리량을 뜻하지 않는다.

### 3,000명 비교에서 확인한 한계

- 3,000명은 사전 로그인 20건/초·동시 8개로 150.03초 동안 전원 성공했다. 송금 측정 중 인증 요청은 없었다.
- 목표 흐름 9,600개 중 8,801개를 시작했다. 누락 799개는 account_busy 755개·scheduler_late 44개이며, 겹침 1개는 scheduler_late에 포함돼 있다.
- 실제 송금 시도는 137.42건/초, HTTP 요청 33,952건 중 실패 1,308건, HTTP p95 7.6초였다. 흐름 전체 p95는 약 21.54초였다. 최대 동시 진행 흐름은 2,049개였다.
- 실패는 전송 계층 HTTP 0 992건, HTTP 503 315건, HTTP 500 1건이다. 모든 전송 오류를 하나의 원인으로 확정하지 않는다.
- 같은 측정·응답 대기 구간의 Nginx 로그에서 **4096 worker_connections 부족 경고 1건**을 확인했다. 파일 제한·upstream timeout 표식은 0건이었다.
- 같은 구간의 HAProxy 로그에서 **DOWN 포함 메시지 10개, 사용 가능한 서버 없음 메시지 2개**를 확인했다. 이 메시지 수를 고유 장애 횟수로 단정하지 않는다. 실제 헬스체크 탈락과 연결 한도 도달이 겹친 상태다.
- 같은 구간의 두 API 커널 OOM 표식은 0건이다. 앞선 사전 로그인 OOM과 이 송금 측정의 원인을 섞지 않는다.
- 계정 수만 늘려서는 해결되지 않았다. 160건/초가 온전히 전달되지 않았으므로 137.42를 서버의 절대 최대 TPS라고 부르지 않는다.
- 서버 설정을 추가로 임의 변경하지 않았다. 다음 조사는 Nginx 연결 점유·HAProxy 헬스체크 탈락 시각·API 대기를 함께 다뤄야 한다. 금융 잠금을 제거하는 수정은 하지 않았다.
- 최종 `verify-performance.yml`: API 두 대 worker 4개·풀 20+0·DB 한도 250·TLS 해제 및 Nginx worker 실제 파일 한도 8192 확인. 모든 대상 changed=0, failed=0.
- 최종 `bash deploy/lab.sh verify`: 수집 20/20 UP, DB 복제 두 스레드 정상, MongoDB exporter 인증, Alloy 네 곳 로그 수집, Grafana 데이터소스·10개 대시보드·126개 쿼리 검증 통과.
