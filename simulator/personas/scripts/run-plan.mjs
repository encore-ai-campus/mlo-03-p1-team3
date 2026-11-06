import { createHash, randomBytes } from 'node:crypto'
import { appendFile, mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  SimulatorError, saveState, useStateFile, withCustomerLock, getBaseUrl, apiWait,
  responseResult, submitAndWait, createWriteHooks, authenticate, logIn, accountBalance,
  deposit, transfer, viewLedger, createBrowserPage, closeSession, cleanError, routeUrl, navigatePage, waitForPageReady, waitForApiReads,
} from './run-playwright.mjs'
import { validatePlan, toCustomer, executePlan } from './plan.mjs'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const CATEGORY = { convenience: '편의점', cafe: '카페', restaurant: '음식점', grocery: '마트', gas_station: '주유소', pharmacy: '약국' }
const HELP = '사용법: npm run simulate -- --plan planner/data/plan_YYYY-MM-DD.jsonl --concurrency 10 --allow-remote --headed\n옵션: --profiles FILE (기본: 계획과 같은 폴더의 profiles.json), --dry-run, --retry-failed-reads (실패한 조회만 재시도), --limit N (계획 사용자 수), --all, --once\n전체 계획을 빠르게 재생하며 실제 시각은 서버가 기록합니다. 첫 실행은 600명 가입·초기 입금을 준비합니다.'

export function parsePlanArgs(args) {
  const o = { concurrency: 10, headed: false, allowRemote: false, dryRun: false }
  for (let i = 0; i < args.length; i++) {
    const a = args[i]
    if (['--plan', '--profiles', '--concurrency', '--limit'].includes(a)) {
      const v = args[++i]
      if (!v || v.startsWith('--')) throw new SimulatorError('missing_plan_option_value')
      o[{ '--plan': 'plan', '--profiles': 'profiles', '--concurrency': 'concurrency', '--limit': 'limit' }[a]] = v
    } else if (a === '--headed') o.headed = true
    else if (a === '--allow-remote') o.allowRemote = true
    else if (a === '--dry-run') o.dryRun = true
    else if (a === '--retry-failed-reads') o.retryFailedReads = true
    else if (a === '--help' || a === '-h') o.help = true
    else if (!['--all', '--once'].includes(a)) throw new SimulatorError('unsupported_plan_option')
  }
  o.concurrency = Number(o.concurrency)
  if (!Number.isSafeInteger(o.concurrency) || o.concurrency < 1) throw new SimulatorError('invalid_concurrency')
  if (o.limit !== undefined) {
    o.limit = Number(o.limit)
    if (!Number.isSafeInteger(o.limit) || o.limit < 1) throw new SimulatorError('invalid_limit')
  }
  if (!o.help && !o.plan) throw new SimulatorError('plan_file_required')
  return o
}

// A private seed is generated once in .env; no credentials enter plan JSON or reports.
async function passwordSeed() {
  const path = resolve(ROOT, 'planner/.env')
  let content = ''
  try { content = await readFile(path, 'utf8') } catch (e) { if (e.code !== 'ENOENT') throw e }
  const existing = content.match(/^SIMULATOR_PLAN_PASSWORD_SEED=(.+)$/m)?.[1]?.trim().replace(/^['"]|['"]$/g, '')
  if (existing) {
    if (!/^[a-zA-Z0-9_-]{32,}$/.test(existing) || existing.startsWith('replace_')) throw new SimulatorError('invalid_SIMULATOR_PLAN_PASSWORD_SEED')
    return existing
  }
  const value = randomBytes(32).toString('hex')
  await appendFile(path, `\nSIMULATOR_PLAN_PASSWORD_SEED=${value}\n`, { mode: 0o600 })
  return value
}

function passwordFor(id, seed) {
  return 'Sim' + createHash('sha256').update(seed + ':' + id).digest('hex').slice(0, 24) + '7!'
}

async function navigateRead(page, base, path, endpoint) {
  await waitForPageReady(page)
  const pending = apiWait(page, endpoint, 'GET', { documentPath: path })
  pending.catch(() => {})
  await page.goto(routeUrl(base, path))
  const result = await responseResult(await pending)
  await waitForPageReady(page)
  return result
}

async function loanScreen(page, base) {
  await waitForPageReady(page)
  const products = apiWait(page, '/loans/products', 'GET', { documentPath: '/loan' })
  const loans = apiWait(page, '/loans/me', 'GET', { documentPath: '/loan' })
  products.catch(() => {}); loans.catch(() => {})
  await page.goto(routeUrl(base, '/loan'))
  const result = await responseResult(await products)
  const mine = await responseResult(await loans)
  if (!Array.isArray(result.body)) throw new SimulatorError('loan_products_response_not_array', { requestId: result.requestId, status: result.status })
  if (!Array.isArray(mine.body)) throw new SimulatorError('loan_list_response_not_array', { requestId: mine.requestId, status: mine.status })
  await waitForPageReady(page)
  return { products: result, loans: mine }
}

export function selectLoanProduct(products, params) {
  return products.find(p => params.requested_amount_krw >= p.min_amount
    && params.requested_amount_krw <= p.max_amount && params.requested_amount_krw % p.amount_step === 0
    && p.term_options.includes(params.preferred_term_months)) ?? null
}

export function makeDriver({ browser, base, state, seed, profiles, report }) {
  const customers = new Map(profiles.map(p => [p.sim_user_id, toCustomer(p)]))
  async function newSession(profile, deviceId) {
    const customer = customers.get(profile.sim_user_id)
    const created = await createBrowserPage(browser, base, deviceId)
    return { ...created, customer, profile, closed: false }
  }
  async function logout(s) {
    const result = await closeSession(s.page, base, s.customer, state)
    s.closed = true
    return result
  }
  return {
    errorCode: cleanError,
    async prepare(profile) {
      return withCustomerLock(profile.sim_user_id, async () => {
        const id = profile.sim_user_id, entry = state.customers[id]
        if (entry.write_in_flight) throw new SimulatorError('manual_review_required')
        const s = await newSession(profile, profile.primary_device_id)
        try {
          const auth = await authenticate(s.page, base, s.customer, passwordFor(id, seed))
          entry.session_status = 'authenticated'
          await s.page.waitForURL(routeUrl(base, '/'))
          const me = await navigateRead(s.page, base, '/me', '/auth/me')
          if (!Number.isInteger(me.body?.id)) throw new SimulatorError('backend_user_mapping_missing')
          if (auth.created || (entry.backend_user_id && entry.backend_user_id !== me.body.id)) {
            entry.opening_funded = 0
          }
          entry.backend_user_id = me.body.id
          await saveState(state)
          // The backend caps one deposit at 10 million; larger opening balances use real separate deposits.
          while ((entry.opening_funded ?? 0) < profile.opening_balance_krw) {
            const amount = Math.min(10_000_000, profile.opening_balance_krw - (entry.opening_funded ?? 0))
            const hooks = createWriteHooks(s.customer, 'planner_opening_deposit', state)
            const r = await deposit(s.page, base, amount, 'deposit', hooks)
            entry.opening_funded = (entry.opening_funded ?? 0) + amount
            delete entry.write_in_flight
            await saveState(state)
            await report({ phase: 'prepare', sim_user_id: id, action: 'opening_deposit', outcome: 'success', request_id: r.requestId, http_status: r.status })
          }
          await logout(s)
        } catch (e) {
          if (e.uncertain || entry.write_in_flight) entry.safety_hold = true
          await saveState(state)
          throw e
        } finally { await s.context.close() }
      })
    },
    async open(row) {
      const profile = profiles.find(p => p.sim_user_id === row.sim_user_id)
      const s = await newSession(profile, row.params.sim_device_id)
      try {
        s.result = await logIn(s.page, base, s.customer, passwordFor(row.sim_user_id, seed))
        await s.page.waitForURL(routeUrl(base, '/'))
        state.customers[row.sim_user_id].session_status = 'authenticated'
        return s
      } catch (e) { await s.context.close(); throw e }
    },
    close: logout,
    async dispose(s) {
      if (!s.closed) { try { await logout(s) } catch { /* Cleanup is not counted as a successful plan row. */ } }
      await waitForApiReads(s.page)
      await s.context.close()
    },
    async perform(row, s, ready) {
      const { page, customer } = s, amount = row.params.amount_krw
      const entry = state.customers[customer.id]
      const hooks = createWriteHooks(customer, row.action, state)
      let result
      if (row.action === 'account_view') return navigateRead(page, base, '/accounts', '/accounts/me')
      if (row.action === 'history_view') return viewLedger(page, base)
      if (['transfer', 'withdrawal', 'card_payment'].includes(row.action)) {
        if (await accountBalance(page, base) < amount) return { skipped: 'insufficient_live_balance' }
      }
      if (row.action === 'deposit' || row.action === 'withdrawal') {
        result = await deposit(page, base, amount, row.action === 'withdrawal' ? 'withdraw' : 'deposit', hooks)
      } else if (row.action === 'transfer') {
        const recipient = row.params.recipient_sim_user_id
        if (!ready.has(recipient)) return { skipped: 'planned_recipient_not_ready' }
        const sender = { ...customer, persona: { ...customer.persona, recipient_customer_ids: [recipient] } }
        result = await transfer(page, base, sender, [customers.get(recipient)], amount, hooks)
      } else if (row.action === 'card_payment') {
        await navigatePage(page, routeUrl(base, '/card'))
        await page.getByRole('heading', { name: '카드', exact: true }).waitFor()
        const category = CATEGORY[row.params.merchant_category]
        await page.getByRole('button', { name: category, exact: true }).click()
        const inputs = page.locator('input[name="merchant"]')
        if (!(await inputs.count())) return { skipped: 'planned_merchant_category_unavailable' }
        await inputs.first().check({ force: true })
        await page.getByLabel('결제할 금액').fill(String(amount))
        result = await submitAndWait(page, '/cards/payments', () => page.getByRole('button', { name: /결제하기$/ }).click(), hooks)
        await page.locator('.done-message:not(.visually-hidden)').waitFor()
      } else if (['loan_products', 'loan_view', 'loan_apply'].includes(row.action)) {
        const live = await loanScreen(page, base)
        if (row.action === 'loan_products') return live.products
        if (row.action === 'loan_view') {
          if (row.requires?.includes('existing_loan') && !live.loans.body.some(l => ['pending', 'repaying', 'approved'].includes(l.status))) {
            return { skipped: 'no_existing_live_loan', requestId: live.loans.requestId, status: live.loans.status }
          }
          return live.loans
        }
        if (live.loans.body.some(l => ['pending', 'approved', 'repaying'].includes(l.status))) return { skipped: 'active_live_loan_exists', requestId: live.loans.requestId, status: live.loans.status }
        const product = selectLoanProduct(live.products.body, row.params)
        if (!product) return { skipped: 'no_live_product_matches_planned_terms', requestId: live.products.requestId, status: live.products.status }
        await page.locator(`input[name="loan-product"][value="${product.code}"]`).check({ force: true })
        await page.locator('#loan-amount').fill(String(row.params.requested_amount_krw))
        await page.locator(`input[name="loan-term"][value="${row.params.preferred_term_months}"]`).check({ force: true })
        result = await submitAndWait(page, '/loans/applications', () => page.getByRole('button', { name: /신청/ }).click(), hooks)
        await page.locator('section[aria-labelledby="active-title"]').waitFor()
      } else throw new SimulatorError('unsupported_plan_action')
      delete entry.write_in_flight
      await saveState(state)
      await waitForPageReady(page)
      return result
    },
  }
}

export async function main(args) {
  try {
    const o = parsePlanArgs(args)
    if (o.help) { console.log(HELP); return }
    const path = resolve(o.plan), profilePath = resolve(o.profiles ?? resolve(dirname(path), 'profiles.json'))
    const profiles = JSON.parse(await readFile(profilePath, 'utf8'))
    let rows = (await readFile(path, 'utf8')).split(/\r?\n/).filter(s => s.trim()).map(s => JSON.parse(s))
    validatePlan(profiles, rows)
    if (o.limit) {
      const ids = new Set([...new Set(rows.map(r => r.sim_user_id))].slice(0, o.limit))
      rows = rows.filter(r => ids.has(r.sim_user_id))
    }
    const base = getBaseUrl(o)
    console.log(JSON.stringify({ mode: 'plan', target: base, pool_users: profiles.length,
      active_users: new Set(rows.map(r => r.sim_user_id)).size, plan_rows: rows.length,
      concurrency: o.concurrency, timing: 'accelerated_per_customer_order' }))
    if (o.dryRun) return
    const key = createHash('sha256').update(base).digest('hex').slice(0, 12)
    const stateDir = resolve(ROOT, 'planner/data'), stateFile = resolve(stateDir, `execution-${key}.json`)
    await mkdir(stateDir, { recursive: true })
    const report = async entry => {
      await appendFile(resolve(stateDir, `execution-${key}.jsonl`), JSON.stringify(entry) + '\n', { mode: 0o600 })
      console.log(JSON.stringify(entry))
    }
    // Serialize the whole run as well as individual preparations: no second process can replay this state.
    await withCustomerLock(`planner-${key}`, async () => {
      const seed = await passwordSeed()
      let state
      try { state = JSON.parse(await readFile(stateFile, 'utf8')) }
      catch (e) { if (e.code !== 'ENOENT') throw e; state = { version: 1, customers: {}, plans: {} } }
      useStateFile(state, stateFile)
      const { chromium } = await import('playwright')
      const browser = await chromium.launch({ headless: !o.headed })
      try {
        const driver = makeDriver({ browser, base, state, seed, profiles, report })
        const summary = await executePlan({ profiles, rows, concurrency: o.concurrency, state, save: saveState, report, driver, retryFailedReads: o.retryFailedReads })
        console.log(JSON.stringify({ phase: 'summary', ...summary }))
        if ((summary.outcomes.failed ?? 0) + (summary.outcomes.unknown ?? 0) > 0 || summary.prepared_users < profiles.length) process.exitCode = 1
      } finally { await browser.close() }
    })
  } catch (e) {
    const known = e instanceof SimulatorError ? e.code : [
      'empty_plan_or_profiles', 'invalid_profile', 'invalid_plan_row', 'invalid_planned_amount',
      'invalid_planned_recipient', 'invalid_merchant_category', 'invalid_loan_plan', 'invalid_plan_session',
      'changed_plan_id_requires_new_plan', 'invalid_concurrency',
    ].includes(e.message) ? e.message : e.code === 'ENOENT' ? 'plan_or_profiles_file_missing' : 'plan_execution_failed'
    console.error('simulator plan error: ' + known)
    console.error(HELP)
    process.exitCode = 1
  }
}
