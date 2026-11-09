# 포도 뱅킹 시스템의 데이터 수집 & 관찰

---

> **뱅킹 서비스에서 발생하는 거래·이벤트·로그·메트릭을 수집하고, 데이터의 품질과 활용 가능성을 검증하는 프로젝트**
>
> 뱅킹 서비스를 직접 설계하면서 **데이터 발생 → 수집 → 저장 → 검증 → 관측**을 구현하는 프로젝트입니다.

## 0. 팀 소개

---

### 개주인과 퍼피

| 이름 | 역할 | GitHub |
|---|---|---|
| 목원주 | 추후 기재 | [wonju0516](https://github.com/wonju0516) |
| 박기령 | 추후 기재 | [wrtmm](https://github.com/wrtmm) |
| 이하영 | 추후 기재 | [coffeewoouuu](https://github.com/coffeewoouuu) |
| 조경호 | 추후 기재 | [naelonambul](https://github.com/naelonambul) |

## 1. 프로젝트 소개

---

은행 시스템을 모의 구현해 데이터 발생 환경을 만들고, 데이터를 수집·검증·관측할 수 있는 환경을 구축합니다. 
금융 거래가 정확하게 처리되고, 장애가 발생해도 거래 기록이 유실되지 않는 환경을 구축합니다. 

### 목표

1. **데이터 발생점 구축**: 회원, 입출금, 송금, 카드, 대출 기능을 갖춘 뱅킹 서비스 개발
2. **데이터 수집원**: 업무 DB, 이벤트 DB, 애플리케이션 로그, 시스템 메트릭
3. **데이터 품질 검증**: 누락, 중복, 정합성, 수집 지연 확인
4. **데이터 시각화**: Grafana를 통한 현황 모니터링

## 2. 주요 기능

---

### 2.1 뱅킹 서비스

| 기능 | 주요 내용 |
|---|---|
| 회원 관리 | 회원가입, 로그인, 로그아웃, 회원정보 관리 |
| 입출금 | 계좌 개설, 잔액 조회, 입금 및 출금, 거래 내역 조회 |
| 송금 | 계좌 간 송금, 수취인 관리, 송금 내역 조회 |
| 카드 | 카드 발급, 결제 및 취소, 이용 내역 조회 |
| 대출 | 대출 신청, 심사, 상환, 대출 내역 조회 |

### 2.2 데이터 수집 및 저장

- 사용자 행동 및 금융 거래 이벤트 수집
- MongoDB 기반 이벤트 데이터 저장
- Nginx 및 FastAPI 애플리케이션 로그 수집
- API 성능 및 서버 자원 메트릭 수집
- 데이터 수집 정상 여부 검증

### 2.3 모니터링 및 시각화

- CPU, 메모리 등 서버 자원 사용량
- Grafana 대시보드 구축

## 3. 시스템 아키텍처

---

## 4. erd

---

```mermaid
erDiagram
    accounts {
        bigint id PK
        bigint user_id FK,UK
        varchar account_number UK
        bigint balance
        datetime created_at
    }
    cards {
        bigint id PK
        bigint account_id FK,UK
        char card_number UK
        datetime created_at
    }
    card_payments {
        bigint id PK
        bigint card_id FK
        bigint merchant_id FK
        char transaction_id
        bigint amount
        datetime created_at
    }
    kakao_signups {
        bigint id PK
        char token_hash UK
        varchar kakao_subject
        varchar name
        datetime created_at
        datetime expires_at
    }
    ledger_entries {
        bigint id PK
        char transaction_id
        bigint account_id FK
        varchar entry_type
        bigint amount
        bigint balance_after
        datetime created_at
    }
    loan_applications {
        bigint id PK
        bigint user_id FK
        bigint product_id FK
        varchar product_code
        bigint principal_amount
        smallint term_months
        bigint monthly_installment
        varchar status
        bigint reviewed_by FK
        datetime reviewed_at
        datetime approved_at
        datetime created_at
    }
    loan_products {
        bigint id PK
        varchar code UK
        varchar name
        bigint min_amount
        bigint max_amount
        bigint amount_step
        longtext term_options
    }
    loan_repayments {
        bigint id PK
        bigint loan_application_id FK
        smallint installment_number
        date due_date
        bigint amount
        varchar status
        datetime processed_at
        datetime paid_at
    }
    merchants {
        bigint id PK
        varchar name
        varchar category
        varchar region
        decimal lat
        decimal lng
    }
    schema_migrations {
        varchar version PK
        datetime applied_at
    }
    sessions {
        bigint id PK
        char token_hash UK
        bigint user_id FK
        char device_id
        varchar client
        varchar user_agent
        varchar login_method
        datetime created_at
        datetime last_seen_at
        datetime ended_at
        varchar end_reason
    }
    users {
        bigint id PK
        varchar kakao_subject UK
        varchar phone_number UK
        varchar password_hash
        varchar name
        smallint birth_year
        varchar gender
        varchar marital_status
        tinyint is_employed
        varchar role
        smallint failed_login_count
        datetime locked_until
        datetime created_at
    }
    users ||--o| accounts : "user_id"
    loan_products ||--o{ loan_applications : "product_id"
    users |o--o{ loan_applications : "reviewed_by"
    users ||--o{ loan_applications : "user_id"
    loan_applications ||--o{ loan_repayments : "loan_application_id"
    accounts ||--o{ ledger_entries : "account_id"
    accounts ||--o| cards : "account_id"
    users ||--o{ sessions : "user_id"
    cards ||--o{ card_payments : "card_id"
    merchants ||--o{ card_payments : "merchant_id"
```

## 5. 데이터 수집 설계

---

### 5.1 데이터 수집원

| 수집원 | 데이터 종류 | 수집 내용 | 활용 목적 |
|---|---|---|---|
| MariaDB | 정형 데이터 | 회원, 계좌, 거래, 대출 정보 | 금융 거래 데이터 검증 |
| MongoDB | 반정형 데이터 | 사용자 행동 및 금융 이벤트 | 행동 패턴 및 이상거래 분석 |
| Nginx / FastAPI | 로그 데이터 | 요청, 응답, 오류 로그 | 장애 분석 및 요청 추적 |
| Prometheus | 시계열 데이터 | CPU, 메모리, 응답 시간, 요청 수 | 시스템 성능 모니터링 |

### 5.2 데이터 품질 검증

### 5.3 수집 데이터 활용

## 6. 데이터 검증 및 시각화

---

**목표**

- 사용자 행동 이벤트 생성
- 금융 거래 이벤트 생성
- MongoDB 이벤트 저장
- 이벤트 중복 및 누락 검증

**검증**

- 거래 발생 시 이벤트 생성 여부
- 거래 ID와 이벤트 연결 여부
- 이벤트 스키마 일관성

## 6. 기술 스택

---

| 구분 | 기술 | 역할 |
|---|---|---|
| Backend | Python, FastAPI | 뱅킹 API 개발 |
| RDBMS | MariaDB (Master/Slave) | 업무 데이터 저장 및 복제 |
| NoSQL | MongoDB | 사용자 행동 및 금융 이벤트 저장 |
| Web Server | Nginx | 리버스 프록시 |
| Load Balancer | HAProxy | 백엔드 서버 부하 분산 |
| Metrics | Prometheus | 시스템 및 애플리케이션 메트릭 수집 |
| Log Collector | Grafana Alloy | 로그 수집 및 전달 |
| Log Storage | Grafana Loki | 로그 저장 및 조회 |
| Visualization | Grafana | 모니터링 대시보드 |
| Collaboration | Git, GitHub | 버전 관리 및 협업 |

## 11. 실행 및 재현 방법

---

### 11.1 앱 실행

프론트엔드와 로컬 목 API 서버로 포도뱅크 화면을 시연합니다. 표시되는 계좌, 거래, 카드, 대출은 모두 가상 데이터입니다.

`frontend` 폴더에서 터미널 두 개를 열고 각각 실행합니다.

```powershell
npm run mock:api
```

```powershell
npm run dev:mock
```

개발 서버가 출력하는 주소(기본값 `http://localhost:5173/`)를 브라우저에서 엽니다. 목 API 서버 주소는 `http://127.0.0.1:8001`입니다.

목 서버는 별도의 데이터베이스를 사용하지 않습니다. 계좌 잔액, 거래, 대출 신청은 메모리에만 저장되고 목 API 서버를 다시 시작하면 초기 데이터로 돌아갑니다.

### 11.2 시연 계정으로 로그인

- 전화번호: `01000000000`
- 비밀번호: 비어 있지 않은 임의의 값

목 API 서버에서만 동작하는 시연 계정입니다.

![로그인 전 시작 화면](docs/images/user-manual/01-guest.png)

![로그인 화면](docs/images/user-manual/02-login.png)

### 11.3 홈과 계좌 확인

로그인하면 홈에서 계좌 잔액, 자산 요약, 최근 거래를 확인할 수 있습니다. 하단 메뉴의 **계좌**를 누르면 계좌번호와 거래 내역을 볼 수 있고, 입금·출금·송금 화면으로 이동할 수 있습니다.

![로그인 후 홈](docs/images/user-manual/03-home.png)

![계좌와 거래 내역](docs/images/user-manual/04-accounts.png)

입금 또는 출금 화면에서 금액을 입력하고 아래 버튼을 누릅니다. 금액 빠른 입력 버튼도 사용할 수 있습니다.

![입금 금액 입력](docs/images/user-manual/05-deposit.png)

### 11.4 송금

송금 화면에서 받는 분 전화번호 `01000000001` 또는 계좌번호 `200-1234-0001`을 입력합니다. 이름이 확인되면 금액을 입력하고 **보내기**를 누릅니다. 시연용 수취인은 `이하늘`입니다.

![받는 분과 금액 확인](docs/images/user-manual/06-transfer-ready.png)

완료 화면에서 보낸 금액과 남은 잔액을 확인할 수 있습니다.

![송금 완료](docs/images/user-manual/07-transfer-result.png)

### 11.5 체크카드 결제

하단 메뉴의 **카드**에서 가맹점을 고르고 결제 금액을 입력한 뒤 결제 버튼을 누릅니다. 결제 금액은 목 계좌 잔액과 거래 내역에 반영됩니다.

![카드와 가맹점 선택](docs/images/user-manual/08-card.png)

![결제 금액 입력](docs/images/user-manual/08-card-amount.png)

![카드 결제 완료](docs/images/user-manual/09-card-paid.png)

### 11.6 대출 신청

하단 메뉴의 **대출**에서 상품, 금액, 기간을 선택하고 신청합니다. 목 서버는 신청 상태를 **심사 대기**로 저장합니다.

![대출 신청 입력](docs/images/user-manual/10-loan-application.png)

![대출 심사 대기](docs/images/user-manual/11-loan-pending.png)

### 11.7 내 정보와 도움말

하단 메뉴의 **내 정보**에서 알림 설정, 자주 묻는 질문, 약관 및 개인정보 화면을 확인할 수 있습니다.

![내 정보](docs/images/user-manual/12-my.png)

![알림 설정](docs/images/user-manual/13-notifications.png)

![자주 묻는 질문](docs/images/user-manual/14-faq.png)

![약관 및 개인정보](docs/images/user-manual/15-terms.png)

### 11.8 목 API 범위

- 시연 계정 로그인과 로그아웃
- 계좌 잔액과 거래 내역 조회
- 입금, 출금, 수취인 조회, 송금
- 체크카드 및 가맹점 조회, 결제
- 대출 상품 조회, 신청 및 심사 대기 상태 조회
- 목 데이터는 서버 프로세스 메모리에만 존재하며 재시작 시 초기화

외부 금융 서비스, 실제 계좌, 실제 송금은 연결되어 있지 않습니다.

## 12. 회고

---



