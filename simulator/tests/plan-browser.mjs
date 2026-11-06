// Isolated browser verification against a real frontend build and in-memory API responses.
// No VM, remote API, SQL database or MongoDB connection is made.
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { readFile, mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { resolve, extname } from 'node:path'
import { randomUUID } from 'node:crypto'
import { chromium } from 'playwright'
import { executePlan, withLoanApprovals } from '../personas/scripts/plan.mjs'
import { makeDriver } from '../personas/scripts/run-plan.mjs'
import { useStateFile, saveState } from '../personas/scripts/run-playwright.mjs'

if (!process.argv[2]) throw Error('Pass a built frontend/dist directory')
const dist = resolve(process.argv[2])
await readFile(resolve(dist, 'index.html'))
const temp = await mkdtemp(resolve(tmpdir(), 'podobank-plan-browser-'))
const server = createServer(async (req, res) => {
  try {
    const path = new URL(req.url, 'http://localhost').pathname
    if (path.startsWith('/api/')) { res.writeHead(500); res.end('API must be intercepted'); return }
    const file = path.startsWith('/assets/') ? resolve(dist, '.' + path) : resolve(dist, 'index.html')
    const data = await readFile(file)
    res.writeHead(200, { 'content-type': ({ '.js': 'text/javascript', '.css': 'text/css' })[extname(file)] ?? 'text/html' }); res.end(data)
  } catch { res.writeHead(404); res.end() }
})
await new Promise(r => server.listen(0, '127.0.0.1', r))
const base = `http://127.0.0.1:${server.address().port}`
const browser = await chromium.launch({ headless: true })
const accounts = new Map(), sessions = new Map(), calls = []
const product = { code: 'car', name: '자동차 대출', min_amount: 1000000, max_amount: 50000000, amount_step: 1000000, term_options: [12, 24, 36] }
const observed = [], aborted = [], devices = new Set()
const wrappedBrowser = { async newContext(options) {
  const context = await browser.newContext(options)
  context.on('requestfailed', r => { if (r.url().includes('/api/v1/')) aborted.push(r.url()) })
  await context.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname.replace('/api/v1', '')
    const body = request.postDataJSON() ?? {}, method = request.method()
    const device = request.headers().cookie?.match(/podobank_device=([^;]+)/)?.[1]
    if (device) { assert.match(device, /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/); devices.add(device) }
    const cookie = request.headers().cookie?.match(/test_session=([^;]+)/)?.[1]
    let user = sessions.get(cookie), response = {}, status = 200, extra = {}
    calls.push({ path, method })
    if (path === '/auth/signup') {
      if (accounts.has(body.phone_number)) { status = 409; response = { code: 'phone_already_registered' } }
      else {
        user = { id: accounts.size + 1, name: body.name, role: 'customer', phone: body.phone_number, balance: 0, loans: [], ledger: [] }
        accounts.set(user.phone, user)
        const token = randomUUID(); sessions.set(token, user)
        extra['set-cookie'] = `test_session=${token}; Path=/; HttpOnly; SameSite=Lax`
        response = { status: 'authenticated' }
      }
    } else if (path === '/auth/login') {
      user = accounts.get(body.phone_number)
      if (!user) { status = 401; response = { code: 'invalid_credentials' } }
      else {
        const token = randomUUID(); sessions.set(token, user)
        extra['set-cookie'] = `test_session=${token}; Path=/; HttpOnly; SameSite=Lax`
        response = { status: 'authenticated' }
      }
    } else if (!user) { status = 401; response = { code: 'not_authenticated' } }
    else if (path === '/auth/me') response = { id: user.id, name: user.name, role: user.role }
    else if (path === '/auth/logout') { sessions.delete(cookie); response = { status: 'logged_out' } }
    else if (path === '/accounts/me') response = { account_number: '100-0000-' + user.id, balance: user.balance }
    else if (path === '/accounts/me/ledger') response = { items: user.ledger, limit: 50, offset: 0 }
    else if (path === '/cards/me') response = { card_last4: '1234' }
    else if (path === '/merchants') response = [{ id: 'live-cafe', name: '실제 화면 카페', category: '카페', region: '서울', lat: 37.5, lng: 127.0 }]
    else if (path === '/loans/products') response = [product]
    else if (path === '/loans/me') response = user.loans
    else if (path === '/transfers/recipient-lookup') {
      const recipient = accounts.get(body.query)
      assert.ok(recipient); response = { name: recipient.name }
    } else if (path === '/loans/applications') {
      assert.equal(body.product_code, product.code); assert.equal(body.amount, 21000000)
      response = { application_id: 1, status: 'pending', monthly_installment: 1750000 }
      user.loans.push({ ...response, product_code: product.code, principal_amount: body.amount, term_months: body.term_months, installments: [] })
      observed.push('loan_apply')
    } else if (['/transactions/deposit', '/transactions/withdrawal', '/transfers', '/cards/payments'].includes(path)) {
      if (path === '/transfers') { assert.equal(body.recipient, '01966000002'); assert.equal(body.amount, 103000) }
      if (path === '/cards/payments') { assert.equal(body.merchant_id, 'live-cafe'); assert.equal(body.amount, 49000) }
      user.balance += path.endsWith('/deposit') ? body.amount : -body.amount
      response = { transaction_id: randomUUID(), balance: user.balance }
      observed.push(path)
    } else { status = 404; response = { code: 'unexpected_mock_route' } }
    if (method === 'GET' && ['/accounts/me/ledger', '/loans/me'].includes(path)) await new Promise(r => setTimeout(r, 80))
    await route.fulfill({ status, headers: { 'content-type': 'application/json', 'x-request-id': randomUUID(), ...extra }, body: JSON.stringify(response) })
  })
  return context
} }
try {
  const profiles = [1, 2].map(n => ({ sim_user_id: `sim-000${n}`, persona_type: 'P01', age_band: '30s', is_employed: true,
    primary_device_id: `device-sim-000${n}`, opening_balance_krw: n === 1 ? 12000000 : 1000000, known_recipient_sim_ids: [] }))
  const operations = [ ['login', { sim_device_id: 'new-device-sim-0001' }], ['account_view', {}], ['history_view', {}],
    ['transfer', { amount_krw: 103000, recipient_sim_user_id: 'sim-0002' }],
    ['card_payment', { amount_krw: 49000, merchant_category: 'cafe' }], ['deposit', { amount_krw: 73000 }],
    ['withdrawal', { amount_krw: 17000 }], ['loan_products', {}], ['loan_view', {}],
    ['loan_apply', { selection_strategy: 'choose_from_live_loan_products', requested_amount_krw: 21000000, preferred_term_months: 12 }], ['logout', {}] ]
  const rows = withLoanApprovals(operations.map(([action, params], i) => ({ plan_id: `browser-${i}`, sim_user_id: 'sim-0001', persona_type: 'P01',
    session_key: 'browser-session', planned_at: `2026-11-06T12:${String(i).padStart(2, '0')}:00+09:00`, action, params, execution_status: 'PLANNED' })))
  const state = useStateFile({ version: 1, customers: {}, plans: {} }, resolve(temp, 'state.json'))
  const reports = [], report = async r => reports.push(r)
  let approvals = 0
  const reviewer = { async approve(id, { beforePost }) {
    await beforePost()
    const customer = accounts.get('01966000001'), loan = customer.loans.find(l => l.application_id === id)
    assert.equal(loan.status, 'pending')
    loan.status = 'repaying'
    loan.installments = Array.from({ length: loan.term_months }, (_, i) => ({ number: i + 1, amount: loan.monthly_installment, status: 'scheduled', due_date: '2026-12-06' }))
    customer.balance += loan.principal_amount
    customer.ledger.unshift({ transaction_id: randomUUID(), entry_type: 'loan_disbursement', amount: loan.principal_amount,
      balance_after: customer.balance, created_at: '2026-11-06T12:00:00+09:00' })
    approvals++
    return { body: { status: 'repaying' }, status: 200, requestId: 'isolated-approval-request' }
  } }
  const driver = makeDriver({ browser: wrappedBrowser, base, state, seed: randomUUID(), profiles, report, reviewer })
  const summary = await executePlan({ profiles, rows, concurrency: 2, state, save: saveState, report, driver })
  assert.equal(summary.outcomes.success, 12, JSON.stringify(summary) + '\n' + JSON.stringify(reports.filter(r => r.outcome !== 'success')))
  assert.equal(state.customers['sim-0001'].opening_funded, 12000000)
  assert.equal(state.customers['sim-0001'].backend_user_id, accounts.get('01966000001').id)
  assert.ok(observed.includes('/transfers') && observed.includes('/cards/payments') && observed.includes('loan_apply'))
  assert.ok(reports.filter(r => r.plan_id).every(r => r.request_id && r.http_status === 200))
  assert.equal(aborted.length, 0, 'Navigation aborted a delayed API read')
  assert.equal(devices.size, 3, 'Primary devices must be stable and the new-device session distinct')
  assert.equal(approvals, 1)
  assert.equal(state.plans['browser-9'].application_id, 1)
  assert.equal(state.loanApprovals['browser-9-employee-approval'].status, 'verified')
  const signupCalls = calls.filter(c => c.path === '/auth/signup').length
  const financialCalls = observed.length
  await executePlan({ profiles, rows, concurrency: 2, state, save: saveState, report, driver })
  assert.equal(approvals, 1, 'Completed approvals must never be replayed')
  assert.equal(observed.length, financialCalls, 'Completed financial actions must never be replayed')
  assert.equal(calls.filter(c => c.path === '/auth/signup').length, signupCalls, 'Mapped customers must login directly without duplicate signup attempts')
  console.log('PASS: 12 plan actions including employee approval, customer loan/balance/ledger verification, delayed-read navigation and no financial replay; real frontend/Chromium with isolated API responses.')
} finally {
  await browser.close()
  await new Promise(r => server.close(r))
  await rm(temp, { recursive: true, force: true })
}
