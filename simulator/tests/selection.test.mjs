import assert from 'node:assert/strict'
import test from 'node:test'
import { spawnSync } from 'node:child_process'
import { selectActiveCustomers } from '../personas/scripts/selection.mjs'

const now = new Date('2026-11-06T03:00:00Z') // 금요일 한국 시간 12시
const customer = (id, overrides = {}) => ({ id, persona: {
  preferred_weekdays: [5], preferred_hours: [12], active_days_per_week: 1,
  sessions_per_active_day: 1, ...overrides,
} })

test('한국 시간에 맞는 후보만 선택하고 부족한 인원을 억지로 채우지 않습니다', () => {
  const active = customer('active')
  assert.deepEqual(selectActiveCustomers([
    active, customer('day', { preferred_weekdays: [4] }),
    customer('hour', { preferred_hours: [3] }), customer('inactive', { active_days_per_week: 0 }),
  ], 5, now), [active])
  assert.deepEqual(selectActiveCustomers([customer('none', { preferred_hours: [] })], 5, now), [])
})

test('지정한 최대 인원을 넘지 않으며 같은 사용자를 중복 선택하지 않습니다', () => {
  const customers = Array.from({ length: 10 }, (_, i) => customer(String(i)))
  const selected = selectActiveCustomers(customers, 5, now, () => 0)
  assert.equal(selected.length, 5)
  assert.equal(new Set(selected.map(({ id }) => id)).size, 5)
})

test('주간 접속 빈도에 비례한 추첨 구간을 사용합니다', () => {
  const low = customer('low')
  const high = customer('high', { active_days_per_week: 3, sessions_per_active_day: 3 })
  let highCount = 0
  for (let i = 0; i < 100; i += 1) {
    if (selectActiveCustomers([low, high], 1, now, () => (i + 0.5) / 100)[0] === high) highCount += 1
  }
  assert.equal(highCount, 90)
})

const script = new URL('../personas/scripts/run-playwright.mjs', import.meta.url)
function cli(...args) {
  return spawnSync(process.execPath, [script.pathname, ...args], { encoding: 'utf8' })
}

test('잘못된 동시 접속 수와 없는 사용자는 실행 전에 거부합니다', () => {
  for (const value of ['0', '-1', '1.5', 'abc']) {
    const result = cli('--all', '--once', '--concurrency', value, '--dry-run')
    assert.equal(result.status, 1)
    assert.match(result.stderr, /invalid_value:--concurrency/)
  }
  const missing = cli('--customer-id', 'missing', '--once', '--dry-run')
  assert.equal(missing.status, 1)
  assert.match(missing.stderr, /no_personas_match_scope/)
})

test('브라우저 없는 실행에서도 추첨 인원과 추가 제한을 확인할 수 있습니다', () => {
  const result = cli('--all', '--once', '--concurrency', '5', '--limit', '2', '--dry-run')
  assert.equal(result.status, 0, result.stderr)
  const [summary, ...customers] = result.stdout.trim().split('\n').map(JSON.parse)
  assert.equal(summary.candidate_count, 300)
  assert.equal(summary.concurrency, 5)
  assert.ok(summary.selected_count <= 2)
  assert.equal(customers.length, summary.selected_count)
  assert.equal(new Set(customers.map(({ customer_id }) => customer_id)).size, customers.length)
})

test('이전 simulator 담당 고객도 유형과 ID로 선택할 수 있습니다', () => {
  for (const [scope, value, expected] of [
    ['--profile', 'salary', 80], ['--customer-id', 'customer-006', 1],
  ]) {
    const result = cli(scope, value, '--once', '--dry-run')
    assert.equal(result.status, 0, result.stderr)
    const summary = JSON.parse(result.stdout.trim().split('\n')[0])
    assert.equal(summary.candidate_count, expected)
  }
})
