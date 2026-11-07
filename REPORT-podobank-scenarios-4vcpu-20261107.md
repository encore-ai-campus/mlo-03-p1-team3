# PodoBank VM 증설 및 S1~S4 부하시험 보고서

작성일: 2026-11-07. 실제 측정 결과이며 실패·미측정·불확실 결과를 성공으로 바꾸지 않았습니다.

**결론:** VM 증설과 최종 상태 검증은 완료했습니다. S3 10·20 TPS와 S4는 통과했고, S1·S2 및 S3 40 TPS는 로그인 준비 실패로 정식 측정을 하지 못했습니다. Nginx 연결 한도 초과·HAProxy health 시간 초과·실행기 계정 대기열 고갈을 확인했습니다.

본체 CPU는 시험 실행 구간의 수집 표본에서 최대 94%였으므로 부담이 없다고 말할 수 없습니다. 반면 측정 종료 후 DB 전체 계좌 4,000개의 잔액·원장 불일치와 잘못된 송금 원장 쌍, 음수 잔액은 모두 0건이었습니다. Grafana의 동시 node DOWN 구간은 증설을 위한 정상 종료 시간대였으며 부하시험 중 수집 DOWN 표본은 없었습니다.

## 1. 변경과 시험 범위

- FastAPI 두 대: 각각 2 → **4 vCPU**, 메모리 2GiB·디스크 10GiB 유지. 실행 프로세스는 각 한 개입니다.
- MariaDB master·replica, MongoDB: 각각 **10 → 40GiB**. 실제 게스트 루트 파일시스템은 각각 40,483,942,400바이트(약 37.7GiB)입니다.
- VM 10대와 고정 IP를 유지했습니다. DB 초기화·애플리케이션 코드 변경·프록시 설정 변경은 하지 않았습니다.
- 전체 VM 할당: 20 vCPU, 메모리 17GiB, 가상 디스크 합계 190GiB. 본체는 i5-1340P(12코어·16스레드), RAM 31.64GiB입니다.
- 대상: `http://192.168.219.191` → Nginx → HAProxy → FastAPI 2대 → 분리된 DB VM들. 부하 발생기는 별도 맥북입니다.
- 원본 보고서는 Python·Rust·DB가 같은 4 vCPU/8GB VM에서 실행된 시험입니다. 이번 결과와 차이를 CPU 증설 효과 또는 언어 차이만으로 해석할 수 없습니다. 이번에는 Rust 시험을 실행하지 않았습니다.

| VM | vCPU | RAM GiB | 디스크 GiB |
| --- | --- | --- | --- |
| Nginx | 1 | 1 | 10 |
| HAProxy | 1 | 1 | 10 |
| FastAPI 1 | 4 | 2 | 10 |
| FastAPI 2 | 4 | 2 | 10 |
| MariaDB master | 2 | 2 | 40 |
| MariaDB replica | 1 | 2 | 40 |
| MongoDB | 2 | 2 | 40 |
| Prometheus | 2 | 2 | 10 |
| Loki | 2 | 2 | 10 |
| Grafana | 1 | 1 | 10 |

## 2. 실행 조건과 판정

- 사용자 제공 `scenario.py`를 수정 없이 복사해 실행했습니다. SHA-256은 `source-hashes.json`에 있습니다. Locust 2.47.0을 사용했고 새 의존성은 설치하지 않았습니다.
- 시나리오마다 신규 고객 1,000명, 준비 동시 실행 8, 초당 20명 로그인, 워밍업 10초, 측정 60초, 단계 간 10초 휴지입니다. 시나리오 사이에는 30초 휴지했습니다.
- S1·S2: 600 → 800 → 1,000명. S3: 1,000명으로 10 → 20 → 40 → 80 → 160 → 320 TPS. 첫 기준 미달 단계에서 후속 단계를 중단합니다.
- S4: 1,000명, 10배속, 11:30~13:30을 720초로 축약, 바닥 송금 10 TPS. 밥 결제 비율 90%, 그중 커피 비율 60%로 실행했습니다. 설계 문서의 초안 70%와 다르며 실제 실행 파일 기본값을 따랐습니다. 전체 p95 ≤500ms, 오류율 ≤1%, 목표 인원 유지가 기준입니다.
- 잔액 부족 그룹의 예상 `409 insufficient_funds`는 별도 업무 이름으로 집계합니다. 그 외 실패는 그대로 반영합니다.
- 중요한 원본 실행기 동작: S1~S3에서는 로그인을 마친 사용자가 다른 사용자의 로그인이 끝나기 전에도 업무를 실행합니다. 따라서 준비 실패 단계에도 금융 데이터가 생길 수 있지만, 정식 60초 측정 결과는 없습니다.
- 원본 실행기는 단계 판정 실패여도 프로그램 종료 코드가 0일 수 있습니다. 판정은 `stage-*.json`의 `passed`와 `reason`을 기준으로 읽었습니다.

## 3. 단계 결과

| 시나리오 | 단계 | 로그인 완료 | 요청 | 실패 | 오류율 % | RPS | 전체 p95 ms | 전체 p99 ms | 판정 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 600users | 594 | 미측정 | — | — | — | — | — | ramp_timeout_or_login_failed |
| S2 | 600users | 551 | 미측정 | — | — | — | — | — | ramp_timeout_or_login_failed |
| S3 | 10tps | 1000 | 2000 | 0 | 0.000 | 33.2 | 120 | 230 | 통과 |
| S3 | 20tps | 1000 | 4820 | 0 | 0.000 | 79.99 | 120 | 150 | 통과 |
| S3 | 40tps | 906 | 미측정 | — | — | — | — | — | ramp_timeout_or_login_failed |
| S4 | lunch | 1000 | 30429 | 12 | 0.039 | 42.21 | 160 | 930 | 통과 |

`ramp_timeout_or_login_failed`는 목표 인원을 준비하지 못했다는 뜻입니다. 해당 단계의 업무 RPS·p95를 0으로 해석하면 안 됩니다.

### S1 상세

**600users**

로그인 요청 656건, 실패 시도 62건, 로그인 p95 4200ms. 로그인 재시도와 사용자 재생성 때문에 요청 건수는 사용자 수와 다를 수 있습니다.

| 로그인 실패 종류 | 횟수 |
| --- | --- |
| HTTP 0 ConnectionError: HTTPConnectionPool(host='192.168.219.191', port=80): Max retries exceeded with url: /api/v1/auth/login (Caused by Protoc | 62 |

준비 시간: `{"signup_seconds": 40.63, "deposit_seconds": 15.22, "merchants": {"편의점": 5, "카페": 5, "음식점": 5, "마트": 5, "주유소": 5, "약국": 5}}`

### S2 상세

**600users**

로그인 요청 771건, 실패 시도 220건, 로그인 p95 4300ms. 로그인 재시도와 사용자 재생성 때문에 요청 건수는 사용자 수와 다를 수 있습니다.

| 로그인 실패 종류 | 횟수 |
| --- | --- |
| HTTP 0 ConnectionError: HTTPConnectionPool(host='192.168.219.191', port=80): Max retries exceeded with url: /api/v1/auth/login (Caused by Protoc | 30 |
| HTTP 503 NoneType | 190 |

준비 시간: `{"signup_seconds": 36.51, "deposit_seconds": 15.08, "merchants": {"편의점": 5, "카페": 5, "음식점": 5, "마트": 5, "주유소": 5, "약국": 5}}`

### S3 상세

**10tps**

로그인 요청 1000건, 실패 시도 0건, 로그인 p95 5600ms. 로그인 재시도와 사용자 재생성 때문에 요청 건수는 사용자 수와 다를 수 있습니다.

| 업무 | 요청 | 실패 | RPS | p50 ms | p95 ms | p99 ms |
| --- | --- | --- | --- | --- | --- | --- |
| 송금 | 478 | 0 | 7.93 | 100 | 120 | 130 |
| 송금(잔액부족) | 22 | 0 | 0.37 | 95 | 110 | 110 |
| 조회-받는사람 | 500 | 0 | 8.3 | 48 | 64 | 72 |
| 조회-잔액 | 1000 | 0 | 16.6 | 64 | 92 | 240 |

측정: 2026-11-07T19:12:08.013291+09:00 ~ 2026-11-07T19:13:08.255519+09:00, 60.24초. 부하 발생기 CPU 경고: False. 연결 재시도: 0.

아래 자원은 해당 측정 구간 표본만 사용합니다. CPU는 각 VM의 전체 vCPU를 100%로 정규화한 1분 평균입니다. 메모리는 MemAvailable 기준입니다. 표본은 약 15초+조회 소요 간격이므로 순간 최대를 보장하지 않습니다.

| 서버 | CPU 평균 / 최대 % | 메모리 평균 / 최대 % | 루트 디스크 평균 / 최대 % |
| --- | --- | --- | --- |
| Nginx | 6.8 / 12.3 | 34.6 / 34.6 | 31.1 / 31.1 |
| HAProxy | 7.6 / 13.6 | 35.9 / 35.9 | 31.0 / 31.0 |
| FastAPI 1 | 18.0 / 40.2 | 25.5 / 25.6 | 34.3 / 34.3 |
| FastAPI 2 | 20.8 / 55.0 | 26.1 / 26.1 | 34.2 / 34.2 |
| MariaDB master | 9.5 / 18.7 | 27.2 / 27.2 | 6.3 / 6.3 |
| MariaDB replica | 2.5 / 4.2 | 20.9 / 20.9 | 6.2 / 6.2 |
| MongoDB | 3.3 / 4.8 | 23.7 / 24.3 | 8.5 / 8.5 |
| Prometheus | 1.3 / 1.7 | 25.0 / 25.0 | 29.6 / 29.6 |
| Loki | 2.2 / 2.8 | 20.6 / 20.6 | 25.7 / 25.7 |
| Grafana | 3.2 / 3.2 | 61.0 / 61.0 | 50.0 / 50.0 |

| 본체 표본 수 | 본체 CPU 평균 % | 본체 CPU 최대 % | 본체 사용 가능 RAM 최소 GiB |
| --- | --- | --- | --- |
| 3 | 1.3 | 3 | 19.02 |

**20tps**

로그인 요청 1000건, 실패 시도 0건, 로그인 p95 2900ms. 로그인 재시도와 사용자 재생성 때문에 요청 건수는 사용자 수와 다를 수 있습니다.

| 업무 | 요청 | 실패 | RPS | p50 ms | p95 ms | p99 ms |
| --- | --- | --- | --- | --- | --- | --- |
| 송금 | 1173 | 0 | 19.47 | 100 | 130 | 260 |
| 송금(잔액부족) | 27 | 0 | 0.45 | 89 | 120 | 120 |
| 조회-받는사람 | 1200 | 0 | 19.91 | 49 | 74 | 110 |
| 조회-잔액 | 2420 | 0 | 40.16 | 61 | 92 | 150 |

측정: 2026-11-07T19:14:21.211132+09:00 ~ 2026-11-07T19:15:21.469702+09:00, 60.26초. 부하 발생기 CPU 경고: False. 연결 재시도: 0.

아래 자원은 해당 측정 구간 표본만 사용합니다. CPU는 각 VM의 전체 vCPU를 100%로 정규화한 1분 평균입니다. 메모리는 MemAvailable 기준입니다. 표본은 약 15초+조회 소요 간격이므로 순간 최대를 보장하지 않습니다.

| 서버 | CPU 평균 / 최대 % | 메모리 평균 / 최대 % | 루트 디스크 평균 / 최대 % |
| --- | --- | --- | --- |
| Nginx | 17.3 / 23.6 | 37.9 / 37.9 | 31.1 / 31.1 |
| HAProxy | 21.5 / 29.3 | 37.8 / 38.9 | 31.1 / 31.1 |
| FastAPI 1 | 35.4 / 69.8 | 27.0 / 27.7 | 34.3 / 34.3 |
| FastAPI 2 | 35.1 / 84.5 | 28.4 / 32.8 | 34.2 / 34.3 |
| MariaDB master | 21.3 / 33.8 | 27.6 / 27.6 | 6.3 / 6.3 |
| MariaDB replica | 4.4 / 6.5 | 20.8 / 20.8 | 6.2 / 6.2 |
| MongoDB | 3.9 / 5.4 | 23.7 / 24.1 | 8.5 / 8.5 |
| Prometheus | 1.2 / 1.7 | 25.0 / 25.0 | 29.7 / 29.7 |
| Loki | 6.3 / 8.7 | 21.5 / 21.8 | 25.8 / 25.9 |
| Grafana | 4.2 / 6.5 | 60.8 / 60.8 | 50.0 / 50.0 |

| 본체 표본 수 | 본체 CPU 평균 % | 본체 CPU 최대 % | 본체 사용 가능 RAM 최소 GiB |
| --- | --- | --- | --- |
| 4 | 1.2 | 2 | 19.02 |

**40tps**

로그인 요청 1300건, 실패 시도 394건, 로그인 p95 5300ms. 로그인 재시도와 사용자 재생성 때문에 요청 건수는 사용자 수와 다를 수 있습니다.

| 로그인 실패 종류 | 횟수 |
| --- | --- |
| HTTP 0 ConnectionError: HTTPConnectionPool(host='192.168.219.191', port=80): Max retries exceeded with url: /api/v1/auth/login (Caused by Protoc | 228 |
| HTTP 503 NoneType | 166 |

준비 시간: `{"signup_seconds": 37.64, "deposit_seconds": 15.37, "merchants": {"편의점": 5, "카페": 5, "음식점": 5, "마트": 5, "주유소": 5, "약국": 5}}`

### S4 상세

**lunch**

로그인 요청 1000건, 실패 시도 0건, 로그인 p95 820ms. 로그인 재시도와 사용자 재생성 때문에 요청 건수는 사용자 수와 다를 수 있습니다.

| 업무 | 요청 | 실패 | RPS | p50 ms | p95 ms | p99 ms |
| --- | --- | --- | --- | --- | --- | --- |
| 결제-밥 | 883 | 0 | 1.22 | 27 | 46 | 170 |
| 결제-밥(잔액부족) | 2 | 0 | 0.0 | 22 | 22 | 22 |
| 결제-커피 | 528 | 0 | 0.73 | 23 | 33 | 43 |
| 결제-커피(잔액부족) | 4 | 0 | 0.01 | 24 | 26 | 26 |
| 송금 | 6955 | 0 | 9.65 | 23 | 150 | 450 |
| 송금(잔액부족) | 295 | 0 | 0.41 | 21 | 140 | 1400 |
| 조회-받는사람 | 7250 | 0 | 10.06 | 15 | 92 | 450 |
| 조회-잔액 | 14512 | 12 | 20.13 | 17 | 340 | 1400 |

| 측정 중 오류 | 횟수 |
| --- | --- |
| GET 조회-잔액: HTTP 0 ConnectionError: HTTPConnectionPool(host='192.168.219.191', port=80): Max retries exceeded with url: /api/v1/accounts/me (Caused by Proto | 5 |
| GET 조회-잔액: HTTP 401 authentication_required | 7 |

측정: 2026-11-07T19:19:55.171171+09:00 ~ 2026-11-07T19:31:58.103289+09:00, 720.93초. 부하 발생기 CPU 경고: False. 연결 재시도: 0.

아래 자원은 해당 측정 구간 표본만 사용합니다. CPU는 각 VM의 전체 vCPU를 100%로 정규화한 1분 평균입니다. 메모리는 MemAvailable 기준입니다. 표본은 약 15초+조회 소요 간격이므로 순간 최대를 보장하지 않습니다.

| 서버 | CPU 평균 / 최대 % | 메모리 평균 / 최대 % | 루트 디스크 평균 / 최대 % |
| --- | --- | --- | --- |
| Nginx | 6.0 / 7.2 | 34.4 / 34.6 | 31.2 / 31.2 |
| HAProxy | 7.7 / 10.2 | 38.9 / 40.1 | 31.4 / 31.6 |
| FastAPI 1 | 7.2 / 58.2 | 26.3 / 28.3 | 34.5 / 34.5 |
| FastAPI 2 | 6.8 / 53.9 | 26.9 / 27.6 | 34.4 / 34.5 |
| MariaDB master | 6.6 / 9.8 | 28.7 / 29.8 | 6.4 / 6.4 |
| MariaDB replica | 2.5 / 3.5 | 21.7 / 22.1 | 6.3 / 6.3 |
| MongoDB | 2.2 / 3.3 | 23.9 / 28.2 | 8.5 / 8.6 |
| Prometheus | 0.9 / 1.9 | 24.8 / 25.2 | 29.7 / 29.8 |
| Loki | 2.0 / 5.3 | 22.2 / 22.9 | 25.8 / 25.9 |
| Grafana | 2.7 / 5.4 | 61.3 / 63.4 | 50.0 / 50.0 |

| 본체 표본 수 | 본체 CPU 평균 % | 본체 CPU 최대 % | 본체 사용 가능 RAM 최소 GiB |
| --- | --- | --- | --- |
| 41 | 5 | 37 | 19.12 |

준비 시간: `{"signup_seconds": 37.88, "deposit_seconds": 17.3, "merchants": {"편의점": 5, "카페": 5, "음식점": 5, "마트": 5, "주유소": 5, "약국": 5}}`

### S4 시간대별 송금·결제

| 시간대 | 실제 초 | 송금 시도/초 | 송금 p95 ms | 결제 시도/초 | 결제 p95 ms | 전체 실패 |
| --- | --- | --- | --- | --- | --- | --- |
| 평상시 11:30-12:00 | 180.0 | 10.1 | 290.2 | 0.0 | None | 5 |
| 점심 시작 12:00-12:25 | 150.0 | 9.71 | 45.9 | 0.59 | 570.4 | 0 |
| 밥 결제 12:25-12:35 | 60.0 | 10.8 | 41.5 | 8.58 | 46.4 | 0 |
| 밥+커피 12:35-12:40 | 30.0 | 9.37 | 37.1 | 13.4 | 36.8 | 0 |
| 커피 결제 12:40-12:50 | 60.0 | 9.8 | 31.4 | 6.87 | 33.1 | 0 |
| 감소 12:50-13:00 | 60.0 | 9.9 | 28.7 | 0.0 | None | 0 |
| 복귀 13:00-13:30 | 180.0 | 10.29 | 163.8 | 0.0 | None | 7 |

## 4. 잔액 검증

| 시나리오 | 검증 계좌 | 불일치 | 결과 불확실 | 검증 오류 | 확인 계좌 총액 차이 |
| --- | --- | --- | --- | --- | --- |
| S1 | 1000 | 0 | 0 | 0 | 0 |
| S2 | 387 | 0 | 613 | 0 | 0 |
| S3 | 857 | 0 | 143 | 0 | 0 |
| S4 | 1000 | 0 | 0 | 0 | 0 |

불확실 계좌는 요청 중 연결이 끊기거나 시험 종료 시 응답을 받지 못해 성공 여부를 판단할 수 없는 계좌입니다. 이 계좌들은 잔액 검증에서 제외됩니다. 불일치 0건만으로 전체 계좌의 정합성을 검증했다고 주장하지 않습니다.

## 5. 본체 부담 — 시나리오 전체 실행 구간

아래 표는 업무 유지 구간만이 아니라 가입·입금·로그인·종료 잔액 검증까지 포함합니다. 정식 측정에 진입하지 못한 시험도 포함합니다. VM 정지·디스크 확장 중 표본은 제외했습니다.

| 시나리오 | 표본 수 | CPU 평균 % | CPU 최대 % | 사용 가능 RAM 최소 GiB |
| --- | --- | --- | --- | --- |
| S1 | 9 | 54 | 94 | 12.96 |
| S2 | 8 | 5.4 | 28 | 17.69 |
| S3 | 24 | 4 | 27 | 17.6 |
| S4 | 50 | 5.1 | 37 | 17.88 |

여유 메모리가 남았다는 사실과 CPU 여유는 별개입니다. 로그인 구간에서는 본체 CPU 사용률이 높았으므로 “본체에 부담이 없다”고 결론내릴 수 없습니다. 2 vCPU로 같은 조건의 대조 시험은 이번에 실행하지 않았습니다.

## 6. 확인된 실패 근거와 잠금 해석

- Grafana에서 18:58~19:03:30경 여러 node가 함께 DOWN인 구간은 이번 CPU·디스크 증설을 위해 정상 종료한 유지보수 구간입니다. 게스트 부팅 시각은 19:01:01~19:02:53으로 대조했습니다. 재기동 이후 node의 추가 DOWN 여부는 `node-uptime-evidence.json`으로 확인했습니다. 이 구간은 부하시험 중 node 장애로 분류하지 않습니다.
- Prometheus `up=1`은 해당 시점에 수집에 성공했다는 의미입니다. HAProxy의 2초 health 검사 통과나 금융 업무 정상 응답을 보장하지 않습니다. node 생존·수집 상태와 API 응답 품질을 구분합니다.
- Nginx 실제 설정은 `worker_connections 768`입니다. 시험 중 `768 worker_connections are not enough while connecting to upstream` 경고가 실제 발생했습니다. 클라이언트 연결과 upstream 연결이 모두 연결 한도에 포함됩니다. [Nginx 공식 문서](https://nginx.org/en/docs/ngx_core_module.html#worker_connections)
- HAProxy 로그에 API 두 대의 `Layer7 timeout`(약 2,000ms), 이어 `backend fastapi has no server available!`가 기록됐습니다. 그 구간에서 503이 관측됐습니다. health 응답 지연을 DOWN으로 판정한 사실은 확인됐지만, 지연 내부 원인이 스레드·CPU·DB 연결 대기 중 무엇인지는 분리 측정하지 않았습니다.
- API 커널 OOM 기록과 서비스 재시작은 별도 확인했습니다. 로그인 실패를 메모리 부족 강제 종료라고 단정하지 않습니다. 원본 `oom-check*.log`를 참고하세요.
- 원본 시나리오 실행기의 `BankUser.on_start()`는 `env.pool.popleft()`로 계정을 한 번 소비하며, 고갈 검사를 하지 않습니다. S3 40 TPS 단계에서 `IndexError: pop from an empty deque`가 실제 기록됐습니다. 준비 실패 시 시험 도구 오류까지 섞이므로 해당 단계로 송금 처리 한계를 확정할 수 없습니다.
- HTTP 0은 유효한 HTTP 응답을 받지 못한 클라이언트 표기입니다. 원본 실행기의 예외 문자열이 잘려 있으므로 각 HTTP 0 요청의 세부 원인을 모두 복원할 수는 없습니다.
| DB exporter | 행 잠금 대기 누적 최댓값 | 행 잠금 대기 누적 시간 최댓값 ms |
| --- | --- | --- |
| 192.168.219.195:9104 | 75.0 | 1409.0 |
| 192.168.219.196:9104 | 0.0 | 0.0 |

위 수치는 재기동 이후 DB 전체 누적 값으로 개별 송금 요청의 대기 시간이 아닙니다. 송금 계좌 잠금은 커밋 때 해제되고 MongoDB 쓰기는 그 뒤입니다. 잠금 경합이 존재할 수 있지만 이번 프록시 실패 전체를 잠금 때문이라고 해석할 근거는 없습니다. [MariaDB 공식 상태 변수](https://mariadb.com/docs/server/ha-and-performance/optimization-and-tuning/system-variables/innodb-status-variables)

## 7. 적용·검증과 보존

실행 명령과 원본 결과:

```bash
bash deploy/lab.sh plan
# API 2대 in-place CPU 변경, 0 add / 2 change / 0 destroy
bash deploy/lab.sh apply
# CPU 적용 후 신규 디스크 검사 코드에서 중단: 아래 작업 기록 참고
python3 deploy/lab/resize-db-disks.py
# DB 세 대 각각 40GiB 확인
# 기존 Terraform 상태에서 power_state=on 적용
ansible-playbook -i deploy/lab/.runtime/inventory.json deploy/ansible/resize-db-filesystems.yml
# DB 세 대 failed=0, 실제 파티션·파일시스템 용량 확인
bash deploy/lab.sh verify
# exporters/replica/log pipeline/dashboard query 검증: 첨부 로그 참고
.venv/bin/python -m unittest discover -s deploy/tests -q
# 14 tests OK
bash -n deploy/lab.sh
git diff --check
```

작업 중 새 VMDK 점검 코드가 파일 전체를 읽으려 해 WSL 프로세스가 종료됐습니다. 64KiB 헤더만 읽도록 수정한 뒤 디스크 확장을 재개했습니다. 파티션 번호 출력의 공백으로 growpart 호출이 거부된 부분도 raw 출력으로 수정했습니다. 이후 실제 용량과 재실행을 확인했습니다. 이 유지보수 중단을 부하시험의 OOM 또는 애플리케이션 장애로 집계하지 않았습니다.

수정 파일: `deploy/lab/configure.py`, `deploy/lab.sh`, `deploy/lab/resize-db-disks.py`, `deploy/ansible/resize-db-filesystems.yml`, `deploy/lab/.env.example`. 커밋·푸시는 실행하지 않았습니다.

| 최종 검사 | 실제 결과 | 근거 파일 |
| --- | --- | --- |
| database_invariants | 0 | final-data-check.log |
| filesystem_idempotence | 0 | final-filesystem.log |
| deployment_verification | 0 | final-verification.log |
| terraform_no_drift | 0 | final-plan.log |
| api_oom_and_restarts | 0 | final-api-status.log |
| nginx_limit_evidence | 0 | nginx-limit-evidence.log |
| haproxy_health_evidence | 0 | haproxy-health-evidence.log |
| final_health | True | final-health.json |

종료 코드 0은 해당 검증 명령이 정상 종료했다는 뜻이며, 시나리오 단계 판정과 구분합니다. Terraform 변경 없음은 `final-plan.log`의 실제 계획 문구도 함께 확인했습니다.

| DB 서버 | 실제 저장/정합성 항목 | 건수 |
| --- | --- | --- |
| podobank-mariadb-master | users | 4001 |
| podobank-mariadb-master | accounts | 4000 |
| podobank-mariadb-master | ledger_entries | 39340 |
| podobank-mariadb-master | card_payments | 2248 |
| podobank-mariadb-master | loan_applications | 0 |
| podobank-mariadb-master | balance_mismatches | 0 |
| podobank-mariadb-master | invalid_transfer_pairs | 0 |
| podobank-mariadb-master | negative_balances | 0 |
| podobank-mariadb-replica | users | 4001 |
| podobank-mariadb-replica | accounts | 4000 |
| podobank-mariadb-replica | ledger_entries | 39340 |
| podobank-mariadb-replica | card_payments | 2248 |
| podobank-mariadb-replica | loan_applications | 0 |
| podobank-mariadb-replica | balance_mismatches | 0 |
| podobank-mariadb-replica | invalid_transfer_pairs | 0 |
| podobank-mariadb-replica | negative_balances | 0 |
| podobank-mongodb | podobank_db_records{store="mongodb",dataset="events_bronze",kind="all"} | 40250.0 |
| podobank-mongodb | podobank_db_records{store="mongodb",dataset="card_payment_locations",kind="all"} | 2248.0 |

SQL은 실제 테이블을 읽었고 MongoDB는 최종 강제 갱신한 읽기 전용 집계에서 문서 수를 확인했습니다. MongoDB 집계와 금융 원장은 개별 이벤트 단위 일대일 대사가 아닙니다. 계좌 잔액과 원장 합계, 송금 원장 쌍 검사는 클라이언트 불확실 계좌를 포함한 DB 전체 내부 정합성 검사이며, 끊긴 요청의 사용자 의도나 중복 요청 여부를 복원하지는 않습니다.

**시험 실행 구간의 API 오류 코드 집계**

해당 Loki 조회에서 일치하는 경고/오류 기록이 없습니다. 이는 개별 저장의 완전성을 독립적으로 증명하는 것은 아닙니다.

**시험 실행 구간의 이벤트 저장 경고**

해당 Loki 조회에서 일치하는 경고/오류 기록이 없습니다. 이는 개별 저장의 완전성을 독립적으로 증명하는 것은 아닙니다.

송금·이벤트·DB·앱 로그의 주요 소스 파일 6개가 로컬과 API 두 대에서 SHA-256 기준으로 일치하는지 확인했습니다. 실제 결과: **True**. 이는 전체 저장소 모든 파일의 일치를 주장하는 것은 아닙니다. 근거: `backend-source-verification.json`, `backend-source-hashes.log`.

## 8. 재현 명령과 원본 자료

```bash
/Users/mokwonju/PycharmProjects/mlo-03-p1-team3/.venv/bin/python /Users/mokwonju/Downloads/podobank-scenarios-4vcpu-20261107/scenario.py --host http://192.168.219.191 --tag python-4vcpu --results /Users/mokwonju/Downloads/podobank-scenarios-4vcpu-20261107/results --customers 1000 --warmup 10 --seconds 60 --cooldown 10 --spawn-rate 20 --prepare-concurrency 8 --max-fail-ratio 0.01 --max-p95-ms 500 s1 --stages 600,800,1000
```

```bash
/Users/mokwonju/PycharmProjects/mlo-03-p1-team3/.venv/bin/python /Users/mokwonju/Downloads/podobank-scenarios-4vcpu-20261107/scenario.py --host http://192.168.219.191 --tag python-4vcpu --results /Users/mokwonju/Downloads/podobank-scenarios-4vcpu-20261107/results --customers 1000 --warmup 10 --seconds 60 --cooldown 10 --spawn-rate 20 --prepare-concurrency 8 --max-fail-ratio 0.01 --max-p95-ms 500 s2 --stages 600,800,1000
```

```bash
/Users/mokwonju/PycharmProjects/mlo-03-p1-team3/.venv/bin/python /Users/mokwonju/Downloads/podobank-scenarios-4vcpu-20261107/scenario.py --host http://192.168.219.191 --tag python-4vcpu --results /Users/mokwonju/Downloads/podobank-scenarios-4vcpu-20261107/results --customers 1000 --warmup 10 --seconds 60 --cooldown 10 --spawn-rate 20 --prepare-concurrency 8 --max-fail-ratio 0.01 --max-p95-ms 500 s3 --users 1000 --stages 10,20,40,80,160,320
```

```bash
/Users/mokwonju/PycharmProjects/mlo-03-p1-team3/.venv/bin/python /Users/mokwonju/Downloads/podobank-scenarios-4vcpu-20261107/scenario.py --host http://192.168.219.191 --tag python-4vcpu --results /Users/mokwonju/Downloads/podobank-scenarios-4vcpu-20261107/results --customers 1000 --warmup 10 --seconds 60 --cooldown 10 --spawn-rate 20 --prepare-concurrency 8 --max-fail-ratio 0.01 --max-p95-ms 500 s4 --users 1000 --speed 10 --base-tps 10
```

결과 폴더: `/Users/mokwonju/Downloads/podobank-scenarios-4vcpu-20261107`

- `results/*/stage-*.json`: 단계 판정·업무별 통계·실패 이유
- `results/*/manifest.json`: 준비·실행 조건·잔액 검증
- `results/*/summary.csv`, `by-name.csv`: 공유용 통계
- `s1-runner.log` ~ `s4-runner.log`: 실행 출력, `executions.json`: 실제 명령·시각·종료 코드
- `resources.jsonl`: Windows 본체와 Prometheus 원본 자원 표본
- `environment.json`, `source-hashes.json`, `vm-resources-before-test.log`: 환경·소스 해시·실제 VM 설정
- `final-validation.json`, `final-health.json`, `final-counts.json`, `final-verification.log`: 최종 상태·저장 건수·검증(존재하는 파일만 실제 확인 결과로 사용)

S4의 전체 기간 판정이 통과해도 모든 짧은 시간대가 500ms 이하라는 뜻은 아닙니다. 시간대별 표의 초반 p95 및 전체 p99도 함께 확인해야 합니다. S4의 401 authentication_required는 미사용 10분 세션 만료 규칙과 관련되며 원본 시나리오에는 재로그인 처리가 없습니다. 연결 실패 5건은 세션 만료와 별개입니다.

## 9. 다음 판단

1. CPU/디스크 증설 적용 여부와 부하시험 통과 여부를 분리해야 합니다. 용량 증설은 성능 통과 보장이 아닙니다.
2. Nginx 연결 한도를 늘리는 방안과 로그인 부하를 완만하게 만드는 방안을 비교한 뒤, 사용자가 선택한 조건으로 재시험하는 것이 좋습니다. 이번에는 해당 설정을 임의로 바꾸지 않았습니다.
3. health 시간 초과는 API 내부 대기 시간을 측정해 원인을 구분해야 합니다. 시간 제한을 늘리는 것만으로 업무 성능이 개선됐다고 판단하면 안 됩니다.
4. 40GiB는 초기 용량입니다. 장기 데이터 증가량·로그 보관·백업 공간은 별도 측정이 필요합니다.
5. 사용자 제공 시나리오는 조건마다 1회이며, 원본과 이번 환경이 다릅니다. 절대 최대 인원이나 증설만의 개선 효과를 주장하지 않습니다.
