# PodoBank 현재 운영·배포 현황

기준: 2026-11-08 KST. 현재 실습 환경을 운영하거나 재배포할 팀원을 위한 문서입니다.

## 1. 접속 주소

| 대상 | 주소 |
|---|---|
| Windows/WSL 제어 PC SSH | `ssh playdata@172.30.1.92` |
| 서비스 웹 화면 | http://172.30.1.191/ |
| FastAPI 문서 | http://172.30.1.191/docs |
| 통합 상태 확인 | http://172.30.1.191/api/v1/health |
| Grafana | http://172.30.1.200:3000/ |
| Grafana 운영 요약 | http://172.30.1.200:3000/d/podobank-overview |
| MariaDB 대시보드 | http://172.30.1.200:3000/d/podobank-mariadb |
| MongoDB 대시보드 | http://172.30.1.200:3000/d/podobank-storage |
| Prometheus | http://172.30.1.198:9090/ |
| Loki | http://172.30.1.199:3100/ |

사설 LAN 주소입니다. 접속 가능한 네트워크에서 사용해야 합니다. 로그인 정보·개인키·비밀번호는 이 문서에 포함하지 않습니다.

제어 PC의 프로젝트 작업 경로는 `/home/playdata/podobank-lab`입니다. 명령은 별도 표시가 없으면 이 경로의 WSL Bash에서 실행합니다.

## 2. 요청 및 수집 흐름

```text
브라우저 → Nginx → HAProxy → FastAPI 1 / FastAPI 2 → MariaDB master
                                              └→ MongoDB 이벤트 저장
MariaDB master → MariaDB replica
Nginx·HAProxy·FastAPI 로그 → Alloy → Loki → Grafana
서버·서비스 exporter → Prometheus → Grafana
FastAPI 요청·DB·이벤트 처리 추적 → Tempo → Grafana Explore
```

Nginx는 프론트 정적 파일도 제공합니다. 백엔드 요청은 `/api/` 경로로 HAProxy에 전달됩니다.

## 3. VM 및 자원 구성

| 서버 | IP | vCPU | 할당 RAM |
|---|---|---:|---:|
| nginx | 172.30.1.191 | 1 | 1 GiB |
| haproxy | 172.30.1.192 | 1 | 1 GiB |
| api-1 | 172.30.1.193 | 4 | 2 GiB |
| api-2 | 172.30.1.194 | 4 | 2 GiB |
| mariadb-master | 172.30.1.195 | 4 | 4 GiB |
| mariadb-replica | 172.30.1.196 | 1 | 2 GiB |
| mongodb | 172.30.1.197 | 2 | 2 GiB |
| prometheus | 172.30.1.198 | 1 | 2 GiB |
| loki / Tempo | 172.30.1.199 | 1 | 2 GiB |
| grafana | 172.30.1.200 | 1 | 1 GiB |
| 합계 | 10대 | 20 | 19 GiB |

현재 브리지 네트워크와 기존 VM 디스크를 사용합니다. `resources` 재실행 시 CPU/RAM 변경이 없으면 VM을 중지하지 않는 것을 확인했습니다.

## 4. 실행 설정

- FastAPI: VM당 Uvicorn worker 4개, 총 8개. Uvicorn 접근 로그는 끄고 애플리케이션 요청 로그와 Nginx 접근 로그를 수집합니다.
- DB 풀: worker당 20개, 추가 연결 0개, 풀 대기 5초, 연결 교체 주기 1,800초. `DB_POOL_PRE_PING` 기본값은 false입니다.
- MariaDB: 최대 연결 250개. master InnoDB 버퍼 풀 2 GiB.
- Nginx: worker 연결 4,096개, worker 파일 한도 8,192개, HAProxy upstream keepalive 128개, HTTP/1.1 연결 재사용.
- APM: OpenTelemetry 표본 비율 10%, Loki VM의 Tempo에 저장, Tempo 보관 24시간. 임시 transport 진단 실행기는 기본 운영 경로에서 실행하지 않습니다.
- API→MariaDB TLS: 현재 실습 비교 설정에서는 비활성 상태입니다. 일반 배포 기본값은 TLS 비활성을 강제하지 않습니다. 끊긴 DB 연결은 첫 사용 요청에서 오류가 날 수 있으므로 재시작·장애 상황의 동작은 별도 확인이 필요합니다.

현재 실행 파일과 환경 파일의 주요 위치:

| 항목 | VM 경로 |
|---|---|
| 백엔드 | `/opt/podobank/backend` |
| 프론트 빌드 | Nginx의 `/var/www/podobank` |
| API 비공개 환경 | `/etc/podobank/api.env` |
| worker 풀·TLS 비교 설정 | `/etc/podobank/performance.env` |
| API worker 설정 | `/etc/systemd/system/podobank-api.service.d/workers.conf` |
| API 로그 | `/var/log/podobank/` |

의존성 버전은 `backend/requirements.txt`에 고정돼 있습니다. OpenTelemetry SDK·OTLP exporter·FastAPI instrumentor는 요청 추적용이고, py-spy는 진단용이며 이번 부하시험에서 실행하지 않았습니다.

## 5. DB 유지 및 초기화 정책

**일반 코드 배포·설정 갱신에서는 업무 DB를 삭제하지 않습니다.**

- MariaDB·MongoDB 설치 스크립트와 Ansible 기본값은 데이터 유지입니다.
- 테스트 초기화 playbook은 명시적인 확인값이 없으면 서비스 중지·데이터 삭제 전에 중단합니다. 확인값이 없는 실행이 `changed=0`으로 거부되는 것을 검증했습니다.
- 초기화는 별도 작업입니다. 일반 재배포 절차에 `reset-test-data.yml`을 포함하지 않습니다.
- 통합 테스트는 전용 `podobank_test` DB를 사용합니다. 테스트가 해당 DB의 테이블·컬렉션을 비우므로 업무 DB 주소를 테스트 환경변수에 넣지 않습니다.
- 테스트 스키마는 master·replica 양쪽에 준비합니다. 테스트 준비 과정의 replica 스키마 누락은 복구했으며, 최종 복제 IO/SQL 스레드 정상·지연 0을 확인했습니다.
- 일반 배포에서 삭제를 막는 보호이며, DB 관리자에게 직접 실행 권한이 있는 모든 수동 삭제를 차단한다는 뜻은 아닙니다.

비공개 설정 파일은 Git으로 공유하지 않습니다.

```text
backend/.env
backend/.env.integration
loadtest/pool/.env
deploy/lab/.env
deploy/vm/vm.env
deploy/vm/monitoring.env
```

필요한 변수명과 가짜 예시는 `.env.example` 계열 파일을 확인합니다. 별도 PC는 해당 PC의 비공개 설정과 접근 권한을 먼저 준비해야 합니다.

## 6. 재배포 및 검증

현재 VM에 검증된 코드·추적·성능 설정·대시보드를 함께 반영할 때:

```bash
cd /home/playdata/podobank-lab
bash deploy/lab.sh upgrade
bash deploy/lab.sh verify
```

현재의 **DB TLS 비활성 실습 조건을 명시적으로 유지할 때만** 다음과 같이 실행합니다.

```bash
bash deploy/lab.sh upgrade -e performance_disable_db_tls=true
```

작업별 명령:

| 명령 | 범위 |
|---|---|
| `bash deploy/lab.sh upgrade` | 기존 VM에 백엔드·APM·성능 설정·대시보드 반영. DB 초기화 없음. API 순차 재시작 가능 |
| `bash deploy/lab.sh observability` | DB 읽기 전용 집계·Grafana 대시보드 반영 및 검증 |
| `bash deploy/lab.sh performance` | worker·풀·DB 한도·Nginx 성능 설정. API 재시작 가능 |
| `bash deploy/lab.sh resources` | 기존 VM의 CPU/RAM만 변경. 계획을 검사하고 변경 대상 VM만 중지·기동 |
| `bash deploy/lab.sh verify` | exporter·DB 복제·로그 수집·Grafana·쿼리 확인 |

`resources`는 신규 생성·삭제·디스크·네트워크 변경이 계획에 섞이면 거부합니다. DB master 4 GiB 확인 전에는 버퍼 풀 2 GiB 적용도 거부합니다.

`apply`는 전체 VM 중단을 포함하는 다른 작업입니다. 단순 코드 재배포에 사용하지 않습니다. 현재 주소를 유지하는 재배포에는 인벤토리를 다시 생성할 필요가 없습니다.

## 7. Grafana 화면

현재 기존 대시보드 10개를 사용합니다.

- 상단: CPU·메모리·디스크의 **시간별 사용률 그래프**. 자원 사용률 숫자 카드는 제거했습니다.
- 운영 요약: 요청·2xx/4xx/5xx·응답 지연·HTTP 응답 추이·총 적재 현황.
- DB 화면: **총 저장 행/문서 수·저장 용량·시간별 추이**. 테이블별·업무 종류별 건수 표는 제거했습니다.
- MariaDB 총 행 수는 관측 대상 회원·계좌·세션·원장·카드 결제·대출 테이블의 합계이며 금융 거래 수가 아닙니다. 복제본을 중복 합산하지 않습니다.
- MongoDB 총 문서 수는 업무 이벤트와 카드 위치 컬렉션의 합계입니다.
- DB 저장 용량은 MariaDB 데이터+인덱스 할당량, MongoDB storageSize+indexSize입니다. OS 디스크 전체 사용량과 구분합니다.
- DB 집계는 2분 주기입니다. 표본·수집이 없는 상태를 임의로 0건으로 채우지 않습니다.
- 운영 요약과 FastAPI의 요청·오류·지연은 여러 worker의 `request_completed` 로그를 Loki에서 집계합니다. Loki에 도착한 기록 기준이며 외부 클라이언트의 전송 실패 전체를 뜻하지는 않습니다.

마지막 반영 후 10개 대시보드 read-back·쿼리 140개 실행과 브라우저 화면을 확인했습니다.

## 8. 검증 결과

### 기능·동시성·배포

| 실행 | 결과 |
|---|---|
| `backend`에서 `../.venv/bin/pytest tests -q --tb=short` (전용 테스트 환경변수 설정) | 435 passed, 기존 TestClient deprecation warning 1개 |
| 저장소 루트 `.venv/bin/python -m unittest discover -s loadtest/tests -q` | 37 tests OK |
| 저장소 루트 `.venv/bin/pytest deploy/tests -q` | 23 passed, 4 subtests passed |
| 변경 백엔드·부하 발생기 Python 파일 `ruff check` | 통과 |
| `git diff --check` | 통과 |

백엔드 테스트는 별도 MariaDB·MongoDB에서 실행했습니다. 동시 송금·일일 한도 경쟁·연결 풀 고갈·원장 검증을 포함합니다. SQLite로 대체하지 않았습니다. 전체 저장소의 모든 파일에 대한 린트 통과를 주장하는 결과는 아닙니다.

### 실제 VM 부하시험

1,000개 준비 계정을 재사용했습니다. 사전 로그인은 초당 20개 예약·동시 최대 8개이며 전원 성공 후 측정했습니다. 각 단계 워밍업 10초, 측정 60초입니다. 측정 중 로그인·가입·입금 준비 호출은 없습니다.

한 흐름: 잔액 조회 → 수취인 조회 → 송금 → 잔액 조회.

| 목표 흐름/초 | 실제 송금 시도/초 | HTTP 요청 | HTTP 실패 | 전체 HTTP p95 | 일정 누락 | 판정 |
|---:|---:|---:|---:|---:|---:|---|
| 80 | 80 | 19,200 | 0 | 72ms | 0 | 통과 |
| 160 | 160 | 38,400 | 0 | 130ms | 0 | 통과 |

예상한 잔액 부족 응답은 별도 시나리오로 분류합니다. 송금 시도 수가 성공한 금융 거래 수와 항상 같은 것은 아닙니다. p95는 송금 API 단독이나 흐름 전체가 아닌 **전체 HTTP 요청** 기준입니다.

- 종료 잔액: 1,000개 확인, 불확실 0·불일치 0·조회 오류 0.
- 업무 DB master·replica: 계좌 16,000개, 원장 151,636개로 일치.
- 잔액-원장 불일치·깨진 송금 쌍·음수 잔액: 양쪽 모두 0건.
- 최종 수집 대상 20/20 UP, API 두 대 정상, 복제 IO/SQL 정상·지연 0, Alloy 네 곳 로그 수집 정상.
- Tempo에서 실제 송금의 인증·DB 획득·SQL·금융 처리·이벤트 저장·스레드 대기 구간을 Grafana 경유로 조회했습니다.

이 수치는 검증 시점 기록입니다. 이후 사용자 요청이나 부하시험으로 건수와 자원 사용량은 달라집니다.

### 재실행 예시

부하 발생 PC의 프로젝트 루트에서 실행합니다. 해당 PC의 가상환경과 비공개 시험 계정 풀을 먼저 준비해야 합니다.

```bash
.venv/bin/python loadtest/split_scenarios.py transfer \
  --host http://172.30.1.191 --allow-remote \
  --accounts 1000 --pool-env loadtest/pool/.env \
  --prelogin-rate 20 --prelogin-concurrency 8 \
  --rates 80,160 --warmup 10 --seconds 60
```

실제 업무 DB에 시험 송금·이벤트가 추가됩니다. 금융 요청을 자동 재시도하지 않습니다. 시험 계정의 현재 잔액을 기준으로 종료 잔액을 확인합니다.

## 9. 반영 상태와 남은 범위

- 현재 VM과 Grafana에는 위 코드·설정·화면이 반영돼 있습니다.
- 팀 공유 시 이 문서가 포함된 PR의 main 반영 여부를 확인하고 해당 버전을 사용합니다. 재배포할 제어 PC에도 같은 버전의 코드를 준비해야 합니다. 비공개 환경 파일은 각 제어 PC에서 별도로 관리합니다.
- 이번 부하시험은 기존 데이터로 한 60초 시험입니다. 1년치 데이터 재생성·장시간 안정성·최대 처리량은 검증하지 않았습니다.
- 여러 설정과 코드가 함께 반영됐으므로 성능 향상을 특정 변경 하나의 효과로 단정하지 않습니다.
- 기능·부하시험 통과가 모든 장애·중복 거래·장기 운영의 안전성을 증명하지는 않습니다.

## 팀 전달용 3줄

```text
현재 10대 VM에 백엔드·APM·배포 설정을 반영했고, DB master 4 vCPU/4GB·버퍼 풀 2GB 및 전체 20 vCPU/19GB 구성을 사용합니다.
실제 VM에서 80·160흐름/초가 HTTP 실패·일정 누락 없이 통과했으며(p95 72·130ms), 기능·동시성 테스트와 잔액·원장·복제 검증도 통과했습니다.
Grafana는 시간별 CPU·메모리·디스크와 DB 총 적재량 중심으로 구성했고, 일반 재배포는 데이터를 유지합니다. 현재 구성과 재배포·검증 명령은 운영 현황 문서에 정리했습니다.
```
