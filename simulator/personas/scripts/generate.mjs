import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile, unlink } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const base = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = async (path) => JSON.parse(await readFile(resolve(base, path), 'utf8'));
const config = await read('config/distribution.json');
const rules = await read('config/behavior-rules.json');
let state = config.seed >>> 0;
function random() {
  state += 0x6d2b79f5;
  let x = state;
  x = Math.imul(x ^ (x >>> 15), x | 1);
  x ^= x + Math.imul(x ^ (x >>> 7), x | 61);
  return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
}
const integer = (min, max) => Math.floor(random() * (max - min + 1)) + min;
const choose = (values) => values[integer(0, values.length - 1)];
const amount = ([min, max]) => integer(min / 1000, max / 1000) * 1000;
function shuffle(values) {
  const result = [...values];
  for (let i = result.length - 1; i > 0; i--) {
    const j = integer(0, i);
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}
function personalRange([min, max]) {
  const center = amount([min, max]);
  return [Math.max(min, Math.floor(center * 0.7 / 1000) * 1000),
    Math.min(max, Math.ceil(center * 1.3 / 1000) * 1000)];
}
assert.equal(Object.values(config.types).reduce((a, b) => a + b, 0), config.total_customers);
const genders = shuffle(Array.from({ length: 300 }, (_, i) => i < 150 ? 'female' : 'male'));
const customers = [];
const groups = {};
for (const [type, count] of Object.entries(config.types)) {
  const rule = rules.types[type];
  assert.ok(rule);
  assert.ok(count >= config.playwright_customers_per_type);
  const group = [];
  for (let i = 0; i < count; i++) {
    const index = customers.length;
    const id = `customer-${String(index + 1).padStart(3, '0')}`;
    const isNew = i < config.new_customers_per_type;
    const loanProduct = choose(['car', 'jeonse', 'home']);
    const term = choose({ car: [12, 24, 36, 48, 60, 120], jeonse: [12, 24], home: [120, 240, 360] }[loanProduct]);
    const principal = integer(1, 10) * 1000000;
    const customer = {
      id,
      signup: {
        name: `가상고객${String(index + 1).padStart(3, '0')}`,
        phone_number: `010${String(index + 1).padStart(8, '0')}`,
        birth_year: config.reference_year - integer(20, 79),
        gender: genders[index], marital_status: choose(['single', 'married']),
        is_employed: random() < 0.7,
      },
      persona: {
        type, label: rule.label, lifecycle: isNew ? 'new' : 'established',
        preferred_client: choose(['web', 'ios-app', 'android-app']),
        preferred_weekdays: shuffle([1, 2, 3, 4, 5, 6, 7]).slice(0, integer(2, 5)).sort(),
        preferred_hours: shuffle(rule.preferred_hours).slice(0, 2).sort((a, b) => a - b),
        timing_jitter_minutes: integer(5, 45),
        active_days_per_week: integer(...rule.active_days_per_week),
        sessions_per_active_day: integer(...rule.sessions_per_active_day),
        weekly_targets: Object.fromEntries(['transfers', 'card_payments', 'ledger_views', 'withdrawals']
          .map((name) => [name, integer(...rule[`${name}_per_week`])])),
        transfer_amount_range: personalRange(rule.transfer_amount_range),
        card_payment_amount_range: personalRange(rule.card_payment_amount_range),
        withdrawal_amount_range: personalRange(rule.withdrawal_amount_range),
        preferred_merchant_categories: shuffle(['카페', '음식점', '편의점', '마트', '주유소', '약국']).slice(0, 2),
        funding: {
          mode: rule.funding.mode, amount: amount(rule.funding.amount_range),
          day_of_month: rule.funding.mode === 'monthly' ? choose([5, 10, 15, 20, 25]) : null,
          weekday: rule.funding.mode === 'weekly' ? integer(1, 7) : null,
          interval_days: rule.funding.mode === 'irregular' ? integer(...rule.funding.interval_days_range) : null,
        },
        initial_funding_amount: isNew ? 0 : amount(rule.initial_balance_range),
        reserve_balance: amount(rule.reserve_balance_range),
        insufficient_funds_policy: 'skip_and_wait_for_funding',
        loan_plan: type === 'loan' ? {
          product_code: loanProduct, principal_amount: principal, term_months: term,
          review_expected: 'approved',
          repayment_reserve: Math.ceil(principal / term),
          note: '승인은 직원 API, 상환은 일별 배치가 담당합니다.',
        } : null,
      },
      execution: {
        owner: i < config.playwright_customers_per_type ? 'playwright' : 'simulator',
        timezone: config.timezone,
        actual_client: i < config.playwright_customers_per_type ? 'web' : 'preferred_client',
        exclusive_customer_lock: true,
      },
    };
    customer.execution.actual_client = customer.execution.owner === 'playwright' ? 'web' : customer.persona.preferred_client;
    group.push(customer);
    customers.push(customer);
  }
  groups[type] = group;
}
// Internal IDs link synthetic plans only; runtime must map API-issued account IDs.
for (const customer of customers) {
  customer.persona.recipient_customer_ids = shuffle(customers.filter((c) => c.id !== customer.id))
    .slice(0, integer(2, 5)).map((c) => c.id);
}
const newUsers = customers.filter((c) => c.persona.lifecycle === 'new').map((c) => ({
  customer_id: c.id, steps: ['signup', 'first_deposit', 'recipient_lookup', 'first_transfer'],
  first_deposit_amount: 300000, first_transfer_amount: 10000,
  preconditions: ['수취인이 가입되어 있어야 합니다.'], after_completion: 'established',
}));
const eligible = shuffle(customers.filter((c) => c.persona.lifecycle === 'established'));
const scenarios = [
  ['login_failure_spike', 8, { failed_attempts: 5, window_minutes: 2, wait_for_unlock_seconds: 301 },
    ['로그아웃 상태에서 실행합니다.', '마지막 실패 뒤 잠금 시간이 지난 후 정상 로그인합니다.'], '실패·잠금·잠금 해제 후 로그인 결과를 확인합니다.'],
  ['rapid_transfer_spike', 8, { transfer_attempts: 8, window_minutes: 5, amount: 10000 },
    ['잔액 80000원 이상과 가입된 수취인을 준비합니다.'], '송금 결과마다 원장과 이벤트를 대조합니다. 반복 송금 자체는 차단 조건이 아닙니다.'],
  ['insufficient_funds_burst', 8, { withdrawal_attempts: 3, requested_balance_ratio: 1.2 },
    ['잔액을 조회하고 잔액보다 크면서 1회 한도 이하인 금액을 사용합니다.', '조건을 만족하지 않으면 건너뛰고 사유를 기록합니다.'], '잔액 부족 실패 후 잔액·원장이 변하지 않는지 확인합니다.'],
  ['high_value_transfer', 6, { amount: 5000000, transfer_attempts: 1 },
    ['잔액 5000000원 이상과 당일 송금 한도를 확인합니다.'], '정상 고액 송금이 발생하고 금액 구간이 기록되는지 확인합니다.'],
];
let offset = 0;
const assignments = scenarios.flatMap(([scenario, count, parameters, preconditions, expected]) =>
  eligible.slice(offset, offset += count).map((c) => ({
    customer_id: c.id, scenario, parameters, preconditions, expected,
    activation: 'explicit_run_only', temporary: true, pause_normal_actions: true,
  })));
const loanCustomer = customers.find((c) => c.persona.type === 'loan' && c.persona.lifecycle === 'established');
assignments.push({ customer_id: loanCustomer.id, scenario: 'repayment_overdue_recovery',
  activation: 'explicit_run_only', temporary: true, pause_normal_actions: true,
  preconditions: ['승인된 대출과 도래한 상환 회차를 준비합니다.', '납부액보다 적은 잔액으로 배치를 실행하고 다음 날 충분히 충전합니다.'],
  expected: '연체 후 다음 날 자동 재시도로 납부되며 원장과 잔액이 일치해야 합니다.' });
const contract = {
  version: 2, synthetic: true, seed: config.seed,
  timezone: config.timezone,
  runtime_rules: [
    '기본 비밀번호는 고객 ID에서 파생하며, 필요하면 Git 제외 로컬 자격 증명 파일로 합성 고객별 값을 지정합니다. 로그에는 기록하지 않습니다.',
    '고객별 owner만 실행하며 담당 변경 전 실행 잠금을 인계합니다.',
    '실제 잔액·세션·대출 상태와 발급된 계좌·카드 ID는 실행 상태 저장소에서 관리합니다.',
    '초기 자금과 정기 충전은 입금 API로 처리하여 원장을 남깁니다.',
    '일반 거래는 잔액에서 reserve_balance와 대출 repayment_reserve를 뺀 가용액 안에서 실행합니다.',
    '잔액 부족 시 자동 무한 충전하지 않고 다음 충전까지 기다립니다.',
    '수취인 조회 성공 후 송금하며 가맹점은 API가 반환한 업종과 ID에 매핑합니다.',
    '배치 기준은 실제 한국 날짜입니다. 시간 압축만으로 상환일이 바뀌지 않습니다.',
    '검증 상황은 명시적으로 활성화하고 평소 행동과 분리합니다.',
    '실행 기록에는 시도·응답·request_id를 남기고 이벤트 스키마에 개인정보를 추가하지 않습니다.',
  ],
};
const outputs = new Map(Object.entries(groups).map(([type, group]) => [
  `profiles/${type}.json`, { ...contract, type, label: rules.types[type].label, count: group.length, customers: group },
]));
outputs.set('profiles/index.json', { ...contract, total_customers: customers.length,
  profiles: Object.entries(groups).map(([type, group]) => ({ type, label: rules.types[type].label,
    count: group.length, file: `${type}.json` })),
});
outputs.set('scenarios/new-users.json', { version: 2, assignments: newUsers });
outputs.set('scenarios/anomaly-users.json', { version: 2,
  description: '이상 징후와 실패 복구 검증용 일시적 상황입니다. 사기 여부를 판정하지 않습니다.', assignments });
// Validate before replacing outputs.
assert.equal(customers.length, 300);
assert.equal(new Set(customers.map((c) => c.id)).size, 300);
assert.equal(new Set(customers.map((c) => c.signup.phone_number)).size, 300);
const ids = new Set(customers.map((c) => c.id));
for (const c of customers) {
  assert.ok(c.persona.recipient_customer_ids.every((id) => ids.has(id) && id !== c.id));
  for (const field of ['transfer_amount_range', 'card_payment_amount_range', 'withdrawal_amount_range']) {
    const [min, max] = c.persona[field];
    assert.ok(Number.isInteger(min) && min > 0 && min <= max && max <= 10000000);
  }
}
assert.ok([...newUsers, ...assignments].every((a) => ids.has(a.customer_id)));
for (const [path, value] of outputs) {
  await mkdir(dirname(resolve(base, path)), { recursive: true });
  await writeFile(resolve(base, path), `${JSON.stringify(value, null, 2)}\n`);
}
// Replace the explicitly retired aggregate, preserving unrelated files.
await unlink(resolve(base, 'profiles/customers.json')).catch((error) => {
  if (error.code !== 'ENOENT') throw error;
});
console.log(`고객 ${customers.length}명 / 유형 ${Object.keys(groups).length}개 / 신규 ${newUsers.length}명 / 검증 상황 ${assignments.length}명`);
console.log(`Playwright ${customers.filter((c) => c.execution.owner === 'playwright').length}명 / 시뮬레이터 ${customers.filter((c) => c.execution.owner === 'simulator').length}명`);
