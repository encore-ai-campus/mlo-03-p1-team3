import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import { validatePlan, workerPool, executePlan, fingerprint, toCustomer } from '../personas/scripts/plan.mjs'
import { parsePlanArgs, selectLoanProduct } from '../personas/scripts/run-plan.mjs'

const profiles = JSON.parse(await readFile(new URL('../planner/samples/profiles.json', import.meta.url)))
const rows = (await readFile(new URL('../planner/samples/plan_2026-11-06.jsonl', import.meta.url), 'utf8')).trim().split('\n').map(JSON.parse)
const sampleSession = () => structuredClone(validatePlan(profiles, rows).find(g => g.some(r => r.action === 'card_payment')))
const driver = (overrides = {}) => ({
  prepare: async () => {}, open: async () => ({ result: { requestId: 'real-login', status: 200 } }),
  close: async () => ({ requestId: 'real-logout', status: 200 }), dispose: async () => {},
  perform: async () => ({ requestId: 'real-request', status: 200 }), errorCode: e => e.code ?? 'browser_interaction_failed', ...overrides,
})
async function execute(selected, state, d) {
  const reports = []
  const summary = await executePlan({ profiles, rows: selected, concurrency: 10, state,
    driver: d, save: async () => {}, report: async r => reports.push(r) })
  return { reports, summary }
}

test('새 샘플은 600명 풀과 400명 전체 행동이며 모든 세션이 유효합니다', () => {
  const sessions = validatePlan(profiles, rows)
  assert.equal(profiles.length, 600)
  assert.equal(new Set(rows.map(r => r.sim_user_id)).size, 400)
  assert.equal(sessions.flat().length, 2640)
  const customers = profiles.map(toCustomer)
  assert.equal(new Set(customers.map(c => c.signup.phone_number)).size, 600)
  assert.ok(customers.every(c => !('password' in c.signup)))
})

test('동시 10명 제한으로 400명 모두 처리합니다', async () => {
  let active = 0, peak = 0, completed = 0
  await workerPool(Array.from({ length: 400 }), 10, async () => {
    peak = Math.max(peak, ++active)
    await new Promise(resolve => setImmediate(resolve))
    --active; ++completed
  })
  assert.equal(peak, 10); assert.equal(completed, 400)
})

test('전체 계획을 실행하고 같은 고객은 겹치지 않으며 모든 계획 ID를 기록합니다', async () => {
  const active = new Set()
  let performed = 0, prepared = 0
  const { reports, summary } = await execute(rows, {}, driver({
    prepare: async () => { prepared++ },
    open: async row => {
      assert.ok(!active.has(row.sim_user_id)); active.add(row.sim_user_id)
      return { id: row.sim_user_id, result: { requestId: 'login', status: 200 } }
    },
    perform: async () => { performed++; return { requestId: 'backend-rid', status: 200 } },
    dispose: async s => { active.delete(s.id) },
  }))
  assert.equal(prepared, 600)
  assert.equal(summary.planned_users, 400)
  assert.equal(reports.length, 2640)
  assert.equal(performed, rows.filter(r => !['login', 'logout'].includes(r.action)).length)
  assert.equal(summary.outcomes.success, 2640)
  assert.ok(reports.every(r => r.plan_id && r.request_id && r.http_status === 200 && r.actual_at.endsWith('+09:00')))
})

test('완료한 계획을 재실행해도 로그인과 금융 작업을 반복하지 않습니다', async () => {
  const selected = sampleSession(), state = {}
  await execute(selected, state, driver())
  const second = await execute(selected, state, driver({ open: async () => assert.fail('replayed session') }))
  assert.equal(second.reports.length, 0)
})

test('금융 응답이 불명확하면 unknown을 기록하고 이후 작업을 중지합니다', async () => {
  const selected = sampleSession(), state = {}
  const first = await execute(selected, state, driver({ perform: async r => {
    if (r.action === 'card_payment') throw Object.assign(Error(), { uncertain: true, code: 'response_unknown', requestId: 'pending-rid' })
    return { status: 200 }
  } }))
  assert.ok(first.reports.some(r => r.outcome === 'unknown' && r.request_id === 'pending-rid'))
  assert.equal(state.customers[selected[0].sim_user_id].safety_hold, true)
  await execute(selected, state, driver({ perform: async () => assert.fail('retried uncertain payment') }))
})

test('중단된 started 기록은 자동 재전송하지 않습니다', async () => {
  const selected = sampleSession(), payment = selected.find(r => r.action === 'card_payment')
  const state = { plans: { [payment.plan_id]: { fingerprint: fingerprint(payment), outcome: 'started' } } }
  await execute(selected, state, driver({ open: async () => assert.fail('unsafe replay') }))
  assert.equal(state.customers[payment.sim_user_id].safety_hold, true)
})

test('동일 계획 ID의 금액 변경과 잘못된 수신인은 실행 전에 거부합니다', async () => {
  const selected = sampleSession(), state = {}
  await execute(selected, state, driver())
  selected.find(r => r.action === 'card_payment').params.amount_krw++
  await assert.rejects(execute(selected, state, driver()), /changed_plan_id/)
  const transfer = structuredClone(rows.find(r => r.action === 'transfer'))
  transfer.params.recipient_sim_user_id = 'missing'
  assert.throws(() => validatePlan(profiles, [transfer]), /invalid_planned_recipient/)
})

test('실제 상품 금액·기간에 맞지 않으면 상품을 임의로 바꾸지 않습니다', () => {
  const product = { code: 'live', min_amount: 1000000, max_amount: 30000000, amount_step: 1000000, term_options: [12] }
  const params = { requested_amount_krw: 21000000, preferred_term_months: 12 }
  assert.equal(selectLoanProduct([product], params), product)
  assert.equal(selectLoanProduct([product], { ...params, preferred_term_months: 360 }), null)
})

test('계획 dry-run은 10명만 뽑지 않고 전체 400명을 보여줍니다', () => {
  const result = spawnSync(process.execPath, ['personas/scripts/run-playwright.mjs', '--plan',
    'planner/samples/plan_2026-11-06.jsonl', '--all', '--once', '--concurrency', '10', '--dry-run'],
  { cwd: new URL('..', import.meta.url), encoding: 'utf8' })
  assert.equal(result.status, 0, result.stderr)
  const summary = JSON.parse(result.stdout)
  assert.equal(summary.pool_users, 600); assert.equal(summary.active_users, 400)
  assert.equal(summary.plan_rows, 2640); assert.equal(summary.concurrency, 10)
  assert.throws(() => parsePlanArgs(['--plan', 'x', '--watch']), /unsupported_plan_option/)
})

test('실패한 조회만 재시도하며 준비 입금·완료된 금융 작업은 재실행하지 않습니다', async () => {
  const selected = sampleSession()
  const paymentIndex = selected.findIndex(r => r.action === 'card_payment')
  const lookup = { ...selected[paymentIndex], plan_id: 'retry-read', action: 'loan_view', params: {}, planned_at: selected[paymentIndex].planned_at }
  selected.splice(paymentIndex + 1, 0, lookup)
  const state = {}
  await execute(selected, state, driver({ perform: async row => {
    if (row.action === 'loan_view') throw Error('old read failure')
    return { status: 200 }
  } }))
  for (const profile of profiles) state.customers[profile.sim_user_id].backend_user_id = 1
  const pendingPayment = structuredClone(selected[paymentIndex])
  pendingPayment.plan_id = 'never-started-payment'
  selected.splice(paymentIndex + 1, 0, pendingPayment)
  const performed = []
  await executePlan({ profiles, rows: selected, concurrency: 10, state, retryFailedReads: true,
    save: async () => {}, report: async () => {}, driver: driver({
      prepare: async () => assert.fail('must not signup or fund'),
      perform: async row => { performed.push(row.action); return { status: 200, requestId: 'retry-rid' } },
    }) })
  assert.deepEqual(performed, ['loan_view'])
  assert.equal(state.plans['retry-read'].outcome, 'success')
  assert.equal(state.plans['never-started-payment'], undefined)
  assert.equal(state.plans[selected[paymentIndex].plan_id].outcome, 'success')
})
