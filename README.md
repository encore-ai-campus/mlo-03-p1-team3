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

![시스템 아키텍처](docs/images/banking_system_architecture.drawio.svg)

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

## 12. 회고

---



