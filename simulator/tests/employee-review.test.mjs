import test from 'node:test'
import assert from 'node:assert/strict'
import { makeEmployeeReviewer, verifyDisbursement } from '../personas/scripts/employee-review.mjs'
import { withLoanApprovals, validatePlan } from '../personas/scripts/plan.mjs'

const profile = { sim_user_id: 'sim-0001', persona_type: 'P04', age_band: '30s', is_employed: true,
  primary_device_id: 'primary', opening_balance_krw: 0 }
const rows = ['login', 'loan_apply', 'logout'].map((action, i) => ({ plan_id: `test-${i}`,
  sim_user_id: profile.sim_user_id, persona_type: 'P04', session_key: 'test-session',
  planned_at: `2026-11-06T12:0${i}:00+09:00`, action, execution_status: 'PLANNED',
  params: action === 'login' ? { sim_device_id: 'primary' } : action === 'loan_apply'
    ? { selection_strategy: 'choose_from_live_loan_products', requested_amount_krw: 1000000, preferred_term_months: 12 } : {} }))

function requestFactory({ role = 'bank_employee', approvalFailure = false } = {}) {
  const calls = [], contexts = []
  const request = { async newContext(options) {
    const context = { options, disposed: false, async dispose() { this.disposed = true },
      async fetch(path, options) {
        calls.push([path, options.method])
        if (path.endsWith('/approve') && approvalFailure) throw Error('private request body must not leak')
        const body = path === '/api/v1/auth/me' ? { role }
          : path.endsWith('/approve') ? { status: 'repaying' } : { status: 'authenticated' }
        return { status: () => 200, ok: () => true, headers: () => ({ 'x-request-id': 'safe-request-id' }), json: async () => body }
      } }
    contexts.push(context); return context
  } }
  return { request, calls, contexts }
}
const credentials = { phone_number: '01000000000', password: 'example-only-password' }

test('승인은 신청 직후 별도 계획으로 추가되고 기존 계획 내용은 유지됩니다', () => {
  const before = structuredClone(rows), expanded = withLoanApprovals(rows)
  assert.deepEqual(rows, before)
  assert.deepEqual(expanded.map(r => r.action), ['login', 'loan_apply', 'loan_approve', 'logout'])
  assert.equal(expanded[2].params.application_plan_id, rows[1].plan_id)
  validatePlan([profile], expanded)
  assert.deepEqual(withLoanApprovals(expanded), expanded)
  const wrong = structuredClone(expanded); wrong[2].params.application_plan_id = 'another-plan'
  assert.throws(() => validatePlan([profile], wrong), /invalid_loan_approval_plan/)
})

test('직원은 격리된 API 세션으로 지정한 신청만 승인하고 로그아웃합니다', async () => {
  const mock = requestFactory(), reviewer = makeEmployeeReviewer({ request: mock.request, base: 'http://localhost', credentials })
  let began = false
  const result = await reviewer.approve(42, { beforePost: async () => { began = true } })
  assert.equal(began, true); assert.equal(result.body.status, 'repaying')
  assert.deepEqual(mock.calls.map(c => c[0]), ['/api/v1/auth/login', '/api/v1/auth/me', '/api/v1/admin/loans/42/approve', '/api/v1/auth/logout'])
  assert.ok(mock.contexts[0].disposed)
})

test('고객 권한으로는 승인하지 않고 세션을 정리합니다', async () => {
  const mock = requestFactory({ role: 'customer' })
  const reviewer = makeEmployeeReviewer({ request: mock.request, base: 'http://localhost', credentials })
  await assert.rejects(reviewer.approve(42), e => e.code === 'employee_role_required')
  assert.equal(mock.calls.filter(c => c[0].endsWith('/approve')).length, 0)
  assert.ok(mock.contexts[0].disposed)
})

test('승인 응답이 유실되면 불명확한 금융 결과로 처리하고 자동 재전송하지 않습니다', async () => {
  const mock = requestFactory({ approvalFailure: true })
  const reviewer = makeEmployeeReviewer({ request: mock.request, base: 'http://localhost', credentials })
  await assert.rejects(reviewer.approve(42), e => e.uncertain && e.code === 'loan_approval_response_unknown' && !e.message.includes('private'))
  assert.equal(mock.calls.filter(c => c[0].endsWith('/approve')).length, 1)
  assert.ok(mock.contexts[0].disposed)
})


test('다른 고객의 동시 입금은 허용하되 대출 입금 중복이나 잔액 불일치는 거부합니다', () => {
  const before = [{ transaction_id: 'prior', amount: 100, balance_after: 100 }]
  const payment = { transaction_id: 'loan', entry_type: 'loan_disbursement', amount: 1000000, balance_after: 1000100 }
  const incoming = { transaction_id: 'incoming', entry_type: 'transfer_in', amount: 500, balance_after: 1000600 }
  assert.ok(verifyDisbursement(100, before, 1000600, [incoming, payment, ...before], 1000000))
  assert.equal(verifyDisbursement(100, before, 1000000, [payment, ...before], 1000000), false)
  assert.equal(verifyDisbursement(100, before, 2000100, [{ ...payment, transaction_id: 'duplicate', balance_after: 2000100 }, payment, ...before], 1000000), false)
})
