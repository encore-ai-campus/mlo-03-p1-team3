# Persona Playwright simulator

## 새 페르소나 계획을 Playwright로 실행

새 계획은 `--plan`으로 연결합니다. 아래 명령은 `simulator` 폴더에서 실행합니다.

```bash
SIMULATOR_BASE_URL=http://192.168.0.191 npm run simulate -- --plan planner/samples/plan_2026-11-06.jsonl --concurrency 10 --allow-remote --headed
```

- 처음에는 계획과 같은 폴더의 `profiles.json`에 있는 **600명 전원**을 실제 가입·로그인하고, 초기 잔액은 화면에서 입금합니다. 송금 상대도 실제 가입되어 있어야 하므로 하루 비활성 고객까지 준비합니다. 초기 잔액이 1천만 원을 넘으면 여러 입금으로 나눕니다.
- 이후 계획에 있는 **400명, 2,640개 행동 전체**를 처리합니다. `--concurrency 10`은 최대 동시 접속 수이며 전체 실행 인원을 10명으로 제한하지 않습니다. `--limit 10`을 추가하면 계획 실행만 첫 10명으로 제한합니다. 이때도 가입 준비 대상은 600명입니다.
- 고객별 세션과 행동은 `planned_at` 순서를 지킵니다. **빠른 재생 방식**이므로 계획의 가상 시각까지 기다리지 않으며, 고객 사이의 전체 시각 순서는 보장하지 않습니다. DB·이벤트의 실제 발생 시각은 백엔드가 기록합니다.
- 송금 수신인, 결제 금액·업종, 대출 금액·기간을 계획에서 읽습니다. 실제 잔액·가맹점·대출 상태를 확인하며 조건이 안 맞으면 `skipped`와 이유를 남깁니다. 다른 수신인이나 금액으로 임의 변경하지 않습니다.
- `initial_loan_stage`는 합성 메타데이터입니다. 심사 대기·상환 상태를 DB에 조작해서 만들지 않습니다. 실제 대출이 필요한 조회는 없으면 건너뛰며, 승인·상환 배치는 이 실행기에 포함되지 않습니다.
- 신규 기기 후보 세션은 계획의 `sim_device_id`를 브라우저 쿠키에 적용합니다. 탐지·부정 거래 성공을 만들어 기록하지 않습니다.

실행 전에 브라우저·서버 호출 없이 전체 인원을 확인하려면 `--dry-run`을 추가합니다.

```bash
SIMULATOR_BASE_URL=http://192.168.0.191 npm run simulate -- --plan planner/samples/plan_2026-11-06.jsonl --concurrency 10 --allow-remote --dry-run
```

날짜별 새 계획은 Python 생성기로 준비합니다. `init`은 기존 프로필을 덮어쓰지 않으므로 최초 한 번만 실행합니다.

```bash
cd planner
python3 persona_sim.py init --output data
python3 persona_sim.py plan --date 2026-11-06 --output data
python3 persona_sim.py validate --date 2026-11-06 --output data
cd ..
SIMULATOR_BASE_URL=http://192.168.0.191 npm run simulate -- --plan planner/data/plan_2026-11-06.jsonl --concurrency 10 --allow-remote --headed
```

`--profiles FILE`로 프로필 경로를 따로 지정할 수 있습니다. 자세한 계획 설명은 [planner/README.md](planner/README.md)를 참고하세요.

### 직원 API로 대출 승인

`--approve-loans`를 붙이면 각 `loan_apply` 바로 뒤에 별도 `loan_approve` 작업을 추가합니다. 고객은 기존 브라우저로 신청하고, 직원은 독립된 Playwright API 세션으로 로그인하여 그 신청만 승인합니다. 직원 화면은 필요하지 않습니다. 실행에는 Node.js 20.12 이상이 필요합니다.

직원 로그인은 저장소 루트의 비공개 `backend/.env`에 있는 `EMPLOYEE_PHONE_NUMBER`, `EMPLOYEE_PASSWORD`를 읽습니다. Ansible로 직원 계정을 먼저 준비해야 합니다. 비밀번호·세션 쿠키는 실행 기록에 저장하지 않습니다. 실제 작업 전에 직원 로그인·권한을 확인합니다.

```bash
SIMULATOR_BASE_URL=http://192.168.0.191 npm run simulate -- --plan planner/samples/plan_2026-11-06.jsonl --concurrency 10 --allow-remote --headed --approve-loans
```

승인 후 고객 브라우저에서 `repaying` 상태, 상환 회차 수, 대출 원금만큼의 잔액 증가와 대출 입금 원장 1건을 확인합니다. 신청 응답의 `application_id`와 승인 결과는 실행 상태에 저장하며, 완료한 신청·승인은 재전송하지 않습니다. 승인 응답이 불명확하거나 승인 후 검증이 실패하면 해당 고객을 보류하고 자동 재시도를 막습니다.

기존 실행 기록에 신청 번호가 없는 과거 대출은 `application_id_not_recorded_for_plan`으로 건너뜁니다. 과거 신청을 검색해 일괄 승인하지 않습니다. 기존 DB에 진행 중인 대출이 있으면 새 신청도 건너뜁니다. `--retry-failed-reads`와 함께 사용할 수 없습니다. `execution-*.json`은 중복 금융 작업을 막는 상태 파일이므로 현재 DB를 유지하는 동안 삭제하지 마세요.

### 실패한 조회만 재검증

화면 전환은 현재 화면의 표시와 진행 중인 API GET 응답 완료를 확인한 뒤 수행합니다. 대출 응답은 새 대출 화면에서 시작된 요청만 받으며, 본문 읽기 실패와 잘못된 배열 응답을 구분해 기록합니다. 기존 계획의 기기 문자열은 안정적인 UUID v5로 변환하므로 같은 기기를 재사용하고 신규 기기 후보만 다른 UUID를 사용합니다.

기존 실행 상태에서 `failed`인 조회(`account_view`, `history_view`, `loan_products`, `loan_view`)만 다시 확인하려면 다음 명령을 사용합니다.

```bash
SIMULATOR_BASE_URL=http://192.168.0.191 npm run simulate -- --plan planner/samples/plan_2026-11-06.jsonl --concurrency 10 --allow-remote --headed --retry-failed-reads
```

이 모드에서는 가입·초기 입금을 실행하지 않습니다. 성공·실패·미실행 상태의 금융 작업도 재전송하지 않고, 조회에 필요한 로그인·로그아웃만 다시 수행합니다. 이전 실패 이력은 JSONL에 유지하고 새 조회 결과를 추가합니다. 기존 대출이 실제로 없으면 HTTP 200 응답을 확인한 뒤 `no_existing_live_loan`으로 건너뜁니다. 대출 상태를 임의로 생성하거나 직원 승인을 실행하지 않습니다.

### 매핑·실행 기록

- 비밀번호 파생용 비밀값은 첫 실제 실행 시 `planner/.env`의 `SIMULATOR_PLAN_PASSWORD_SEED`로 자동 생성합니다. Git에서 제외되며 값을 출력하지 않습니다. 원본 프로필·계획·실행 보고서에 비밀번호를 쓰지 않습니다. 계정이 유지되는 동안 이 파일도 유지해야 합니다.
- `planner/data/execution-<대상 식별자>.json`에 `sim_user_id → backend_user_id`, 준비 입금 진행 상황과 계획별 결과를 저장합니다. 같은 이름의 `.jsonl`에는 계획 ID·실제 요청 ID·HTTP 상태·성공/실패/건너뜀/불명확 결과를 기록합니다. 파일은 Git에서 제외됩니다.
- 같은 계획을 다시 실행해도 기록된 행동을 자동 재전송하지 않습니다. 금융 요청 중 응답을 확인하지 못하거나 프로세스가 끊기면 해당 고객을 보류합니다. 실제 원장을 확인하기 전 임의로 보류를 풀지 마세요.
- DB를 완전히 초기화한 뒤 같은 계획을 새로 실행할 때는 **DB 초기화 확인 후** 해당 대상의 `execution-*.json`·`.jsonl`도 정리해야 합니다. `.env`는 유지합니다. DB가 남아 있는데 실행 상태만 삭제하면 초기 입금을 반복할 수 있습니다.
- MongoDB와 Loki에는 실제 백엔드가 생성하는 이벤트만 들어갑니다. 실행기가 직접 로그나 업무 이벤트를 삽입하지 않습니다. 현재 백엔드의 실제 저장 컬렉션은 `events_bronze`와 결제 위치용 `card_payment_locations`이며, 별도 신규 이벤트 스키마를 저장 경로에 연결하는 변경은 포함하지 않습니다.

### 검증

```bash
npm test
node tests/plan-browser.mjs ../frontend/dist
```

두 번째 명령은 실제 프론트엔드 빌드와 Chromium을 사용하지만 API 응답은 로컬 메모리로 대체합니다. VM의 실제 DB 저장 검증과는 구분됩니다. 화면 조작은 Playwright 공식 [Locator](https://playwright.dev/docs/locators)와 [응답 대기](https://playwright.dev/docs/api/class-page#page-wait-for-response) 방식을 따릅니다.

## 기존 300명 실행기

`--plan` 없이 실행하면 기존 실행기를 사용합니다.

`personas/profiles/*.json`의 전체 300명을 추첨 후보로 사용합니다. 기존 `execution.owner` 값과 관계없이 선택하며, 선호 요일·시간과 활동 빈도에 따라 최대 `--concurrency`명만 실행합니다. Chromium은 기본적으로 창을 표시하지 않는 백그라운드 방식이며, `--headed`를 붙이면 창을 표시합니다. 터미널 종료 후에도 프로세스를 유지하는 기능은 별도입니다.

## 설치

```bash
cd simulator
npm install
npm run install-browser
```

시뮬레이터는 각 고객 ID에서 반복 가능한 가상 비밀번호를 만들어 가입과 이후 로그인을 수행합니다. 특정 합성 고객의 비밀번호를 직접 정하려면 Git에서 제외되는 `personas/state/credentials.local.json`에 고객 ID별 값을 둘 수 있습니다. 비밀번호는 로그에 기록하지 않습니다. `SIMULATOR_BASE_URL`은 선택 사항이며 기본값은 `http://localhost:8080`입니다.

## 한 번 실행

```bash
cd simulator
npm run simulate -- --customer-id customer-001 --once
npm run simulate -- --profile salary --once
npm run simulate -- --all --once
npm run simulate -- --all --once --concurrency 5
```

`--once`는 한국 시간의 현재 요일·시간이 선호 요일·시간에 해당하는 후보 중 사용자를 중복 없이 추첨합니다. 추첨 확률은 `active_days_per_week × sessions_per_active_day`에 비례합니다. 선택된 대상의 로그인 또는 가입과 필요한 첫 입금을 처리한 뒤, 해당 페르소나의 주간 행동 중 실행 가능한 행동을 한 번 수행합니다.

`--concurrency N`은 한 번에 뽑아 실행할 최대 접속자 수입니다(기본 1명). 후보가 부족하면 가능한 인원만 실행하며, 아무도 없으면 접속하지 않습니다. `--customer-id`도 선호 시간 조건을 따릅니다. `--limit N`은 추첨 인원을 추가로 제한하며 파일의 앞 N명으로 후보를 자르지 않습니다. 초기화 단계가 모두 끝난 뒤 행동 단계를 실행하므로 고객마다 두 번 접속할 수 있습니다. 각 단계에서 동시 접속은 지정한 수를 넘지 않습니다.

`--dry-run`을 붙이면 브라우저나 서버를 호출하지 않고 후보 수, 추첨 인원과 계획만 출력합니다. 실행할 때마다 다시 추첨하므로 실제 실행 대상은 달라질 수 있습니다.

## 예약 실행

```bash
cd simulator
npm run simulate:watch -- --all --concurrency 5
```

예약 실행은 초기화 또는 예약 행동·정기 입금이 필요한 사용자 중 현재 선호 요일·시간에 맞는 후보를 같은 방식으로 추첨합니다. 이전 묶음의 접속이 모두 끝난 뒤 `--poll-ms 60000`에 지정한 간격만큼 기다리고 다시 확인합니다. 프로세스는 계속 실행되므로 중지할 때 `Ctrl-C`를 누릅니다.

선택 로직과 옵션 검증은 `npm test`로 확인합니다. 추가 테스트 의존성은 없습니다.

## 동작과 안전

- 브라우저는 모바일 화면 크기의 격리된 Chromium 컨텍스트에서 실행합니다. 모든 업무 동작은 웹 화면을 통해 수행합니다.
- 로그인은 각 실행마다 하며 세션 토큰은 파일로 저장하지 않습니다. 같은 페르소나의 기기 ID는 재사용하고, 실행이 끝나면 화면에서 로그아웃합니다. 실행 상태에는 기기 ID, 최근 잔액, 자원 참조(`me`), 실행 시각, 주간 행동 횟수를 저장합니다.
- 정기 충전은 입금 화면을 사용합니다. 거래 금액은 페르소나의 한도와 reserve 금액 안에서 고르고, 잔액이 부족하면 자동 충전하지 않습니다.
- 실행 잠금으로 같은 페르소나의 중복 실행을 막습니다. 로그에는 페르소나 ID, 행동, 결과, 요청 ID만 기록하며 전화번호·비밀번호·잔액·거래 금액은 기록하지 않습니다.
- 금융 요청의 응답을 받지 못해 처리 여부가 불명확하면 자동 재전송하지 않고 해당 페르소나에 안전 보류를 설정합니다. 원장 화면에서 처리 여부를 확인한 뒤 상태 파일의 보류를 해제해야 합니다.
- 기본 URL은 localhost만 허용합니다. 원격 주소는 `--allow-remote`를 명시해야 실행할 수 있습니다.
- 대출 이용형은 고객 화면에서 신청만 합니다. 승인은 직원 API 담당자가 처리합니다. `anomaly-users.json`의 실패·복구 시나리오는 일반 행동과 분리되어 자동 실행하지 않습니다.

상태와 JSONL 실행 기록은 `personas/state/`에 생성되며 Git에서 제외됩니다.
