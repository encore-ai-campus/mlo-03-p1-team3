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
- 계정 자격 증명은 메모리에만 두며 결과 파일에 저장하지 않는다. 전송 오류는 예외 종류만 기록한다.

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
