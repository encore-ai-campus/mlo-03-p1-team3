# Persona Playwright simulator

`personas/profiles/*.json`의 `owner: "playwright"` 고객만 실제 화면에서 실행합니다. 현재는 유형별 5명, 총 30명이며 `owner: "simulator"` 고객은 이 실행기가 건드리지 않습니다.

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
```

`--once`는 대상의 로그인 또는 가입과 필요한 첫 입금을 처리한 뒤, 해당 페르소나의 주간 행동 중 실행 가능한 행동을 한 번 수행합니다. `--dry-run`을 붙이면 브라우저나 서버를 호출하지 않고 대상과 계획만 출력합니다.

## 예약 실행

```bash
cd simulator
npm run simulate:watch -- --all
```

예약 실행은 한국 시간의 요일·시간, 정기 입금 규칙, 주간 행동 목표를 따릅니다. 프로세스는 계속 실행되므로 중지할 때 `Ctrl-C`를 누릅니다. `--poll-ms 60000`으로 확인 간격을 바꿀 수 있습니다.

## 동작과 안전

- 브라우저는 모바일 화면 크기의 격리된 Chromium 컨텍스트에서 실행합니다. 모든 업무 동작은 웹 화면을 통해 수행합니다.
- 로그인은 각 실행마다 하며 세션 토큰은 파일로 저장하지 않습니다. 같은 페르소나의 기기 ID는 재사용하고, 실행이 끝나면 화면에서 로그아웃합니다. 실행 상태에는 기기 ID, 최근 잔액, 자원 참조(`me`), 실행 시각, 주간 행동 횟수를 저장합니다.
- 정기 충전은 입금 화면을 사용합니다. 거래 금액은 페르소나의 한도와 reserve 금액 안에서 고르고, 잔액이 부족하면 자동 충전하지 않습니다.
- 실행 잠금으로 같은 페르소나의 중복 실행을 막습니다. 로그에는 페르소나 ID, 행동, 결과, 요청 ID만 기록하며 전화번호·비밀번호·잔액·거래 금액은 기록하지 않습니다.
- 금융 요청의 응답을 받지 못해 처리 여부가 불명확하면 자동 재전송하지 않고 해당 페르소나에 안전 보류를 설정합니다. 원장 화면에서 처리 여부를 확인한 뒤 상태 파일의 보류를 해제해야 합니다.
- 기본 URL은 localhost만 허용합니다. 원격 주소는 `--allow-remote`를 명시해야 실행할 수 있습니다.
- 대출 이용형은 고객 화면에서 신청만 합니다. 승인은 직원 API 담당자가 처리합니다. `anomaly-users.json`의 실패·복구 시나리오는 일반 행동과 분리되어 자동 실행하지 않습니다.

상태와 JSONL 실행 기록은 `personas/state/`에 생성되며 Git에서 제외됩니다.
