import { createHash, randomUUID } from 'node:crypto'
import { appendFile, mkdir, open, readFile, rename, unlink, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { selectActiveCustomers } from './selection.mjs'
import { runBatch } from './execution.mjs'

const BASE = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const STATE_DIR = resolve(BASE, 'state')
const STATE_FILE = resolve(STATE_DIR, 'runtime.json')
const RUN_LOG = resolve(STATE_DIR, 'runs.jsonl')
const CREDENTIALS_FILE = resolve(STATE_DIR, 'credentials.local.json')
const TIME_ZONE = 'Asia/Seoul'
const DEFAULT_URL = 'http://localhost:8080'
const API_PREFIX = '/api/v1'
const WEEK_ACTIONS = ['transfers', 'card_payments', 'ledger_views', 'withdrawals']

class SimulatorError extends Error {
  constructor(code, { requestId = null, uncertain = false } = {}) {
    super(code)
    this.code = code
    this.requestId = requestId
    this.uncertain = uncertain
  }
}

function parseArgs(args) {
  const result = {
    help: false,
    once: false,
    watch: false,
    dryRun: false,
    headed: false,
    all: false,
    allowRemote: false,
    customerId: null,
    profile: null,
    limit: null,
    concurrency: 1,
    pollMs: 60_000,
  }
  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i]
    if (arg === '--help' || arg === '-h') result.help = true
    else if (arg === '--once') result.once = true
    else if (arg === '--watch') result.watch = true
    else if (arg === '--dry-run') result.dryRun = true
    else if (arg === '--headed') result.headed = true
    else if (arg === '--all') result.all = true
    else if (arg === '--allow-remote') result.allowRemote = true
    else if (arg === '--customer-id') result.customerId = takeValue(args, ++i, arg)
    else if (arg === '--profile') result.profile = takeValue(args, ++i, arg)
    else if (arg === '--concurrency') result.concurrency = positiveInteger(takeValue(args, ++i, arg), arg)
    else if (arg === '--limit') result.limit = positiveInteger(takeValue(args, ++i, arg), arg)
    else if (arg === '--poll-ms') result.pollMs = positiveInteger(takeValue(args, ++i, arg), arg)
    else throw new SimulatorError(`unknown_option:${arg}`)
  }
  if (!result.help && (result.once === result.watch)) {
    throw new SimulatorError('choose_exactly_one_mode:--once_or_--watch')
  }
  if (!result.help && [result.all, Boolean(result.customerId), Boolean(result.profile)].filter(Boolean).length !== 1) {
    throw new SimulatorError('choose_exactly_one_scope:--all_--customer-id_--profile')
  }
  if (result.dryRun && result.watch) throw new SimulatorError('dry_run_supports_once_only')
  return result
}

function takeValue(args, index, name) {
  const value = args[index]
  if (!value || value.startsWith('--')) throw new SimulatorError(`missing_value:${name}`)
  return value
}

function positiveInteger(value, name) {
  const parsed = Number(value)
  if (!Number.isSafeInteger(parsed) || parsed < 1) throw new SimulatorError(`invalid_value:${name}`)
  return parsed
}

function usage() {
  return [
    '사용법:',
    '  npm run simulate -- --customer-id customer-001 --once',
    '  npm run simulate -- --profile salary --once',
    '  npm run simulate -- --all --once',
    '  npm run simulate:watch -- --all',
    '',
    '옵션:',
    '  --customer-id ID   한 페르소나 실행',
    '  --profile TYPE     한 유형의 전체 페르소나를 추첨 후보로 사용',
    '  --all              전체 300명 페르소나를 추첨 후보로 사용',
    '  --once             지금 한 번 로그인하고 예정 행동 1회를 실행',
    '  --watch            한국 시간 기준 예약 행동을 계속 확인',
    '  --dry-run          브라우저를 열지 않고 대상과 계획만 확인',
    '  --headed           화면이 보이는 Chromium으로 실행',
    '  --concurrency N    현재 시간에 맞는 후보 중 최대 N명 추첨·동시 실행 (기본 1)',
    '  --limit N          추첨 인원 추가 제한 (파일 순서와 무관)',
    '  --poll-ms N        --watch 확인 간격 (기본 60000ms)',
    '  --allow-remote     localhost 이외의 SIMULATOR_BASE_URL 허용',
    '',
    '비밀번호는 customer ID에서 자동 생성하며 환경 변수가 필요 없습니다.',
    '선택 환경 변수: SIMULATOR_BASE_URL (기본 http://localhost:8080)',
  ].join('\n')
}

async function loadPersonas() {
  const index = await readJson(resolve(BASE, 'profiles/index.json'))
  const allCustomers = []
  for (const profile of index.profiles ?? []) {
    const data = await readJson(resolve(BASE, 'profiles', profile.file))
    for (const customer of data.customers ?? []) {
      allCustomers.push({ ...customer, persona: { ...customer.persona, profile_type: profile.type } })
    }
  }
  const newScenario = await readJson(resolve(BASE, 'scenarios/new-users.json'))
  const onboarding = new Map((newScenario.assignments ?? []).map((item) => [item.customer_id, item]))
  const customers = allCustomers.map((customer) => ({
    ...customer,
    onboarding: onboarding.get(customer.id) ?? null,
  }))
  return {
    index,
    allCustomers: customers,
    customers,
  }
}

async function readJson(path) {
  return JSON.parse(await readFile(path, 'utf8'))
}

function selectCustomers(customers, options) {
  let selected = customers
  if (options.customerId) selected = selected.filter((customer) => customer.id === options.customerId)
  if (options.profile) selected = selected.filter((customer) => customer.persona.profile_type === options.profile)
  if (!selected.length) throw new SimulatorError('no_personas_match_scope')
  return selected
}

function getBaseUrl(options) {
  const value = process.env.SIMULATOR_BASE_URL || DEFAULT_URL
  let url
  try {
    url = new URL(value)
  } catch {
    throw new SimulatorError('invalid_SIMULATOR_BASE_URL')
  }
  if (!['http:', 'https:'].includes(url.protocol) || url.pathname !== '/' || url.search || url.hash) {
    throw new SimulatorError('SIMULATOR_BASE_URL_must_be_an_origin')
  }
  if (!options.allowRemote && !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) {
    throw new SimulatorError('remote_host_requires_--allow-remote')
  }
  return url.origin
}

function routeUrl(baseUrl, path) {
  return new URL(path.replace(/^\//, ''), `${baseUrl}/`).toString()
}

async function loadState() {
  try {
    const value = await readJson(STATE_FILE)
    return value.version === 1 && value.customers ? value : { version: 1, customers: {} }
  } catch (error) {
    if (error.code === 'ENOENT') return { version: 1, customers: {} }
    throw error
  }
}

let stateSaveQueue = Promise.resolve()

function saveState(state) {
  const pending = stateSaveQueue.then(() => persistState(state))
  stateSaveQueue = pending.catch(() => {})
  return pending
}

async function persistState(state) {
  await mkdir(STATE_DIR, { recursive: true })
  const temporary = `${STATE_FILE}.${process.pid}.tmp`
  await writeFile(temporary, `${JSON.stringify(state, null, 2)}\n`, { mode: 0o600 })
  await rename(temporary, STATE_FILE)
}

async function appendRun(entry) {
  await mkdir(STATE_DIR, { recursive: true })
  await appendFile(RUN_LOG, `${JSON.stringify(entry)}\n`, { mode: 0o600 })
}

async function withCustomerLock(customerId, run) {
  await mkdir(STATE_DIR, { recursive: true })
  const lockPath = resolve(STATE_DIR, `${customerId}.lock`)
  let handle
  try {
    handle = await open(lockPath, 'wx', 0o600)
  } catch (error) {
    if (error.code === 'EEXIST') throw new SimulatorError('customer_lock_busy')
    throw error
  }
  try {
    await handle.writeFile(`${JSON.stringify({ pid: process.pid, started_at: new Date().toISOString() })}\n`)
    return await run()
  } finally {
    await handle.close()
    await unlink(lockPath).catch(() => {})
  }
}

function isoNow() {
  return new Date().toISOString()
}

function intlParts(date = new Date()) {
  return Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone: TIME_ZONE,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hourCycle: 'h23', weekday: 'short',
  }).formatToParts(date).filter((part) => part.type !== 'literal').map((part) => [part.type, part.value]))
}

function dateKey(date = new Date()) {
  const p = intlParts(date)
  return `${p.year}-${p.month}-${p.day}`
}

function weekdayNumber(date = new Date()) {
  return ({ Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6, Sun: 7 })[intlParts(date).weekday]
}

function weekStart(date = new Date()) {
  const localDate = dateKey(date)
  const localUtc = new Date(`${localDate}T12:00:00.000Z`)
  localUtc.setUTCDate(localUtc.getUTCDate() - weekdayNumber(date) + 1)
  return localUtc.toISOString().slice(0, 10)
}

function hashInt(value) {
  let hash = 2166136261
  for (const char of value) {
    hash ^= char.charCodeAt(0)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

async function simulatorPassword(customerId) {
  try {
    const overrides = await readJson(CREDENTIALS_FILE)
    const override = overrides[customerId]
    if (override !== undefined) {
      if (typeof override !== 'string' || !/^(?=.*[A-Za-z])(?=.*\d).{8,}$/.test(override)) {
        throw new SimulatorError('invalid_local_simulator_password')
      }
      return override
    }
  } catch (error) {
    if (error.code !== 'ENOENT') throw error
  }
  const suffix = createHash('sha256')
    .update(`podobank-persona:${customerId}`)
    .digest('hex')
    .slice(0, 20)
  return `PodoSim${suffix}7!`
}

function seededInteger(min, max, seed) {
  return min + (hashInt(seed) % (max - min + 1))
}

function seededAmount(range, seed) {
  const [minimum, maximum] = range ?? [0, 0]
  const step = 1000
  const low = Math.ceil(minimum / step) * step
  const high = Math.floor(maximum / step) * step
  if (high < low) return minimum
  return low + (seededInteger(0, Math.floor((high - low) / step), seed) * step)
}

function parseWon(text) {
  const digits = String(text).replace(/[^0-9]/g, '')
  return digits ? Number(digits) : 0
}

function cleanError(error) {
  if (error instanceof SimulatorError) return error.code
  if (error?.name === 'TimeoutError') return 'browser_timeout'
  return 'browser_interaction_failed'
}

function apiWait(page, endpoint, method = 'POST') {
  const expected = `${API_PREFIX}${endpoint}`
  return page.waitForResponse((response) => {
    try {
      const url = new URL(response.url())
      return url.pathname === expected && response.request().method() === method
    } catch {
      return false
    }
  }, { timeout: 30_000 })
}

async function responseResult(response) {
  const requestId = response.headers()['x-request-id'] ?? null
  let body = null
  try {
    body = await response.json()
  } catch {
    // 응답 본문이 없어도 상태 코드와 요청 번호로만 결과를 기록합니다.
  }
  if (!response.ok()) {
    throw new SimulatorError(body?.code ?? `http_${response.status()}`, {
      requestId,
      uncertain: response.status() >= 500,
    })
  }
  return { requestId, body }
}

async function submitAndWait(page, endpoint, click, writeHooks = null) {
  let responsePromise
  let writeStarted = false
  try {
    responsePromise = apiWait(page, endpoint)
    if (writeHooks) {
      await writeHooks.begin()
      writeStarted = true
    }
    await click()
    return await responseResult(await responsePromise)
  } catch (error) {
    responsePromise?.catch(() => {})
    let normalized = error
    if (!(error instanceof SimulatorError)) {
      normalized = error?.name === 'TimeoutError' || writeStarted
        ? new SimulatorError('financial_request_response_unknown', { uncertain: true })
        : new SimulatorError('browser_interaction_failed')
    }
    if (writeHooks && writeStarted) await writeHooks.fail(normalized)
    throw normalized
  }
}

function createWriteHooks(customer, action, state) {
  const entry = state.customers[customer.id]
  return {
    async begin() {
      if (entry.write_in_flight) {
        entry.safety_hold = true
        await saveState(state)
        throw new SimulatorError('manual_review_required_after_interrupted_write')
      }
      entry.write_in_flight = { action, started_at: isoNow() }
      await saveState(state)
    },
    async fail(error) {
      if (error.uncertain) entry.safety_hold = true
      else delete entry.write_in_flight
      await saveState(state)
    },
  }
}

async function logIn(page, baseUrl, customer, password) {
  await page.goto(routeUrl(baseUrl, '/login'))
  await page.getByLabel('전화번호').fill(customer.signup.phone_number)
  await page.getByLabel('비밀번호').fill(password)
  return submitAndWait(page, '/auth/login', () =>
    page.getByRole('button', { name: '로그인', exact: true }).click(),
  )
}

async function signUp(page, baseUrl, customer, password) {
  await page.goto(routeUrl(baseUrl, '/signup'))
  await page.locator('#signup-name').fill(customer.signup.name)
  await page.locator('#signup-phone').fill(customer.signup.phone_number)
  await page.locator('#signup-password').fill(password)
  await page.locator('#signup-password-confirm').fill(password)
  await page.locator('#signup-birth-year').fill(String(customer.signup.birth_year))
  await page.locator(`input[name="gender"][value="${customer.signup.gender}"]`).check({ force: true })
  await page.locator(`input[name="maritalStatus"][value="${customer.signup.marital_status}"]`).check({ force: true })
  await page.locator(`input[name="isEmployed"][value="${String(customer.signup.is_employed)}"]`).check({ force: true })
  await page.locator('#signup-agree').check()
  return submitAndWait(page, '/auth/signup', () =>
    page.getByRole('button', { name: '가입하기', exact: true }).click(),
  )
}

async function authenticate(page, baseUrl, customer, password) {
  if (customer.persona.lifecycle === 'new') {
    try {
      return { created: true, result: await signUp(page, baseUrl, customer, password) }
    } catch (error) {
      if (!(error instanceof SimulatorError) || error.code !== 'phone_already_registered') throw error
      try {
        return { created: false, result: await logIn(page, baseUrl, customer, password) }
      } catch (loginError) {
        if (loginError instanceof SimulatorError && loginError.code === 'invalid_credentials') {
          throw new SimulatorError('existing_persona_password_mismatch', { requestId: error.requestId })
        }
        throw loginError
      }
    }
  }
  try {
    return { created: false, result: await logIn(page, baseUrl, customer, password) }
  } catch (error) {
    if (!(error instanceof SimulatorError) || error.code !== 'invalid_credentials') throw error
    try {
      return { created: true, result: await signUp(page, baseUrl, customer, password) }
    } catch (signupError) {
      if (signupError instanceof SimulatorError && signupError.code === 'phone_already_registered') {
        throw new SimulatorError('existing_persona_password_mismatch', { requestId: signupError.requestId })
      }
      throw signupError
    }
  }
}

async function accountBalance(page, baseUrl) {
  await page.goto(routeUrl(baseUrl, '/accounts'))
  const balance = page.locator('.account-balance').first()
  await balance.waitFor({ timeout: 15_000 })
  return parseWon(await balance.innerText())
}

async function deposit(page, baseUrl, amount, kind = 'deposit', writeHooks = null) {
  if (!Number.isInteger(amount) || amount < 1 || amount > 10_000_000) {
    throw new SimulatorError('amount_out_of_range')
  }
  await page.goto(routeUrl(baseUrl, '/accounts'))
  const actionName = kind === 'withdraw' ? /에서 출금$/ : /에 입금$/
  await page.getByRole('link', { name: actionName }).first().click()
  const inputLabel = kind === 'withdraw' ? '출금할 금액' : '입금할 금액'
  await page.getByLabel(inputLabel).fill(String(amount))
  const endpoint = kind === 'withdraw' ? '/transactions/withdrawal' : '/transactions/deposit'
  const submitName = kind === 'withdraw' ? /출금하기/ : /입금하기/
  return submitAndWait(
    page,
    endpoint,
    () => page.getByRole('button', { name: submitName }).click(),
    writeHooks,
  )
}

async function lookupRecipient(page, baseUrl, customerId, recipients) {
  await page.goto(routeUrl(baseUrl, '/accounts'))
  await page.getByRole('link', { name: /에서 송금$/ }).first().click()
  const query = page.getByLabel('받는 분 전화번호 또는 계좌번호')
  for (const recipient of recipients) {
    if (!recipient || recipient.id === customerId) continue
    const responsePromise = apiWait(page, '/transfers/recipient-lookup')
    await query.fill(recipient.signup.phone_number)
    let response
    try {
      response = await responsePromise
    } catch {
      throw new SimulatorError('recipient_lookup_response_unknown', { uncertain: true })
    }
    let body = null
    try { body = await response.json() } catch { /* 응답 없음 */ }
    if (response.ok()) return { customer: recipient, requestId: response.headers()['x-request-id'] ?? null }
    if (body?.code !== 'recipient_not_found') {
      throw new SimulatorError(body?.code ?? `http_${response.status()}`, {
        requestId: response.headers()['x-request-id'] ?? null,
      })
    }
  }
  return null
}

async function transfer(page, baseUrl, customer, allCustomers, amount, writeHooks = null) {
  const recipientList = (customer.persona.recipient_customer_ids ?? [])
    .map((id) => allCustomers.find((candidate) => candidate.id === id))
    .filter(Boolean)
  const lookup = await lookupRecipient(page, baseUrl, customer.id, recipientList)
  if (!lookup) return { skipped: 'recipient_unavailable' }
  await page.getByLabel('보낼 금액').fill(String(amount))
  const result = await submitAndWait(
    page,
    '/transfers',
    () => page.getByRole('button', { name: /보내기$/ }).click(),
    writeHooks,
  )
  return { ...result, recipientId: lookup.customer.id }
}

async function cardPayment(page, baseUrl, customer, amount, writeHooks = null) {
  await page.getByRole('link', { name: '카드', exact: true }).click()
  await page.getByRole('heading', { name: '카드', exact: true }).waitFor({ timeout: 15_000 })
  const merchantInputs = page.locator('input[name="merchant"]')
  const count = await merchantInputs.count()
  const desired = customer.persona.preferred_merchant_categories ?? []
  let selected = false
  for (let i = 0; i < count; i += 1) {
    const input = merchantInputs.nth(i)
    const label = (await input.getAttribute('aria-label')) ?? ''
    if (desired.some((category) => label.includes(category))) {
      await input.check({ force: true })
      selected = true
      break
    }
  }
  if (!selected && count) await merchantInputs.first().check({ force: true })
  if (!count) return { skipped: 'merchant_unavailable' }
  await page.getByLabel('결제할 금액').fill(String(amount))
  const result = await submitAndWait(
    page,
    '/cards/payments',
    () => page.getByRole('button', { name: /결제하기$/ }).click(),
    writeHooks,
  )
  return result
}

async function viewLedger(page, baseUrl) {
  const responsePromise = apiWait(page, '/accounts/me/ledger', 'GET')
  await page.goto(routeUrl(baseUrl, '/accounts'))
  let response
  try {
    response = await responsePromise
  } catch {
    throw new SimulatorError('ledger_response_unknown')
  }
  if (!response.ok()) throw new SimulatorError(`http_${response.status()}`)
  return { requestId: response.headers()['x-request-id'] ?? null }
}

async function applyForLoan(page, baseUrl, customer, writeHooks = null) {
  const plan = customer.persona.loan_plan
  if (!plan) return { skipped: 'loan_plan_missing' }
  await page.getByRole('link', { name: '대출', exact: true }).click()
  await page.getByRole('heading', { name: '대출', exact: true }).waitFor({ timeout: 15_000 })
  if (await page.getByRole('region', { name: '진행 중 대출' }).count()) return { skipped: 'active_loan_exists' }
  const product = page.locator(`input[name="loan-product"][value="${plan.product_code}"]`)
  if (!(await product.count())) return { skipped: 'loan_product_unavailable' }
  await product.check({ force: true })
  const amountInput = page.locator('#loan-amount')
  await amountInput.fill(String(plan.principal_amount))
  const term = page.locator(`input[name="loan-term"][value="${plan.term_months}"]`)
  if (!(await term.count())) return { skipped: 'loan_term_unavailable' }
  await term.check({ force: true })
  const result = await submitAndWait(
    page,
    '/loans/applications',
    () => page.getByRole('button', { name: /신청/ }).click(),
    writeHooks,
  )
  return result
}

function availableBalance(balance, customer) {
  return Math.max(0, balance - (customer.persona.reserve_balance ?? 0) - (customer.persona.loan_plan?.repayment_reserve ?? 0))
}

function chooseAmount(range, available, seed) {
  const [minimum, maximum] = range ?? [0, 0]
  const cappedMaximum = Math.min(maximum, available, 10_000_000)
  if (cappedMaximum < minimum) return null
  return seededAmount([minimum, cappedMaximum], seed)
}

function chooseAction(customer, state) {
  const week = weekStart()
  const counts = state.customers[customer.id]?.weekly_actions?.[week] ?? {}
  const targets = customer.persona.weekly_targets ?? {}
  const candidates = WEEK_ACTIONS.filter((action) => (targets[action] ?? 0) > (counts[action] ?? 0))
  if (!candidates.length) return null
  const cursor = state.customers[customer.id]?.action_cursor ?? 0
  return candidates[cursor % candidates.length]
}

async function skippedAction(customer, action, reason, entry, state) {
  entry.action_cursor = (entry.action_cursor ?? 0) + 1
  await saveState(state)
  await recordResult(customer, action, { errorCode: reason }, 'skipped')
  return { action, outcome: 'skipped', reason }
}

async function initializeCustomer(page, baseUrl, customer, password, state) {
  const saved = state.customers[customer.id] ?? {}
  if (saved.safety_hold || saved.write_in_flight) {
    saved.safety_hold = true
    state.customers[customer.id] = saved
    await saveState(state)
    throw new SimulatorError('manual_review_required_after_uncertain_write')
  }
  if (saved.credentials_rejected) throw new SimulatorError('persona_credentials_rejected')
  if (saved.login_retry_after && Date.now() < saved.login_retry_after) {
    throw new SimulatorError('persona_login_backoff')
  }
  let auth
  try {
    auth = await authenticate(page, baseUrl, customer, password)
  } catch (error) {
    if (error instanceof SimulatorError && error.code === 'existing_persona_password_mismatch') {
      saved.credentials_rejected = true
      state.customers[customer.id] = saved
      await saveState(state)
    }
    if (error instanceof SimulatorError && error.code === 'account_locked') {
      saved.login_retry_after = Date.now() + 5 * 60_000
      state.customers[customer.id] = saved
      await saveState(state)
    }
    throw error
  }
  const entry = state.customers[customer.id] ?? {}
  entry.initialized = true
  entry.last_seen_at = isoNow()
  entry.session_status = 'authenticated'
  entry.account_ref = 'me'
  entry.card_ref = 'me'
  entry.created_via_signup = auth.created || Boolean(entry.created_via_signup)
  if (auth.created && !entry.initial_funding_completed) {
    entry.initial_funding_pending = customer.onboarding?.first_deposit_amount
      ?? customer.persona.initial_funding_amount
      ?? 0
  }
  state.customers[customer.id] = entry
  await saveState(state)
  await recordResult(customer, auth.created ? 'signup' : 'login', auth.result, 'success')

  if (entry.initial_funding_pending > 0) {
    const hooks = createWriteHooks(customer, 'first_deposit', state)
    const result = await deposit(page, baseUrl, entry.initial_funding_pending, 'deposit', hooks)
    entry.last_funding_at = isoNow()
    entry.last_funding_period = fundingPeriodAt(customer)
    entry.initial_funding_completed = true
    entry.balance = result.body?.balance ?? entry.balance
    delete entry.initial_funding_pending
    delete entry.write_in_flight
    await saveState(state)
    await recordResult(customer, 'first_deposit', result, 'success')
    try {
      entry.balance = await accountBalance(page, baseUrl)
      await saveState(state)
    } catch {
      // POST 응답으로 입금 완료를 확인했으므로 새로고침 실패로 재입금하지 않습니다.
    }
  } else {
    entry.balance = await accountBalance(page, baseUrl)
    if (!entry.last_funding_at) {
      entry.last_funding_at = isoNow()
      entry.last_funding_period = fundingPeriodAt(customer)
    }
    await saveState(state)
  }
  return entry
}

async function runBehavior(page, baseUrl, customer, allCustomers, state, actionName = null) {
  const entry = state.customers[customer.id]
  const beforeBalance = await accountBalance(page, baseUrl)
  const action = actionName ?? chooseAction(customer, state)
  if (!action) return { action: null, outcome: 'skipped', reason: 'weekly_targets_reached' }
  const amountSeed = `${customer.id}:${weekStart()}:${action}:${entry.action_cursor ?? 0}`
  const writeHooks = action === 'ledger_views' ? null : createWriteHooks(customer, action, state)
  let result
  let outcome = 'success'
  try {
    if (action === 'ledger_views') {
      result = await viewLedger(page, baseUrl)
    } else if (action === 'withdrawals') {
      const amount = chooseAmount(customer.persona.withdrawal_amount_range, availableBalance(beforeBalance, customer), amountSeed)
      if (!amount) return await skippedAction(customer, action, 'insufficient_available_balance', entry, state)
      result = await deposit(page, baseUrl, amount, 'withdraw', writeHooks)
    } else if (action === 'transfers') {
      const onboardingTransfer = customer.onboarding && !entry.first_transfer_completed
        ? customer.onboarding.first_transfer_amount
        : null
      const amount = onboardingTransfer
        ?? chooseAmount(customer.persona.transfer_amount_range, availableBalance(beforeBalance, customer), amountSeed)
      if (amount > availableBalance(beforeBalance, customer)) {
        return await skippedAction(customer, action, 'insufficient_available_balance', entry, state)
      }
      if (!amount) return await skippedAction(customer, action, 'insufficient_available_balance', entry, state)
      result = await transfer(page, baseUrl, customer, allCustomers, amount, writeHooks)
      if (result.skipped) return await skippedAction(customer, action, result.skipped, entry, state)
      if (onboardingTransfer) entry.first_transfer_completed = true
    } else if (action === 'card_payments') {
      const amount = chooseAmount(customer.persona.card_payment_amount_range, availableBalance(beforeBalance, customer), amountSeed)
      if (!amount) return await skippedAction(customer, action, 'insufficient_available_balance', entry, state)
      result = await cardPayment(page, baseUrl, customer, amount, writeHooks)
      if (result.skipped) return await skippedAction(customer, action, result.skipped, entry, state)
    } else {
      return { action, outcome: 'skipped', reason: 'unsupported_action' }
    }
  } catch (error) {
    outcome = error instanceof SimulatorError && error.uncertain ? 'unknown' : 'failed'
    if (outcome === 'unknown') entry.safety_hold = true
    else entry.action_cursor = (entry.action_cursor ?? 0) + 1
    await recordResult(customer, action, error, outcome)
    await saveState(state)
    return { action, outcome, reason: cleanError(error), requestId: error.requestId ?? null }
  }
  const week = weekStart()
  entry.weekly_actions ??= {}
  entry.weekly_actions[week] ??= {}
  entry.weekly_actions[week][action] = (entry.weekly_actions[week][action] ?? 0) + 1
  entry.action_cursor = (entry.action_cursor ?? 0) + 1
  entry.last_action_at = isoNow()
  if (Number.isInteger(result.body?.balance)) entry.balance = result.body.balance
  delete entry.write_in_flight
  await saveState(state)
  await recordResult(customer, action, result, outcome)
  try {
    entry.balance = await accountBalance(page, baseUrl)
    await saveState(state)
  } catch {
    // 성공 응답을 확인한 거래는 계좌 화면 새로고침 실패만으로 다시 보내지 않습니다.
  }
  return { action, outcome, requestId: result.requestId ?? null }
}

async function runLoanPlan(page, baseUrl, customer, state) {
  if (!customer.persona.loan_plan || state.customers[customer.id]?.loan_submitted) return null
  try {
    const hooks = createWriteHooks(customer, 'loan_application', state)
    const result = await applyForLoan(page, baseUrl, customer, hooks)
    if (!result.skipped) {
      state.customers[customer.id].loan_submitted = true
      delete state.customers[customer.id].write_in_flight
      await saveState(state)
      await recordResult(customer, 'loan_application', result, 'success')
      return { action: 'loan_application', outcome: 'success', requestId: result.requestId ?? null }
    }
    return { action: 'loan_application', outcome: 'skipped', reason: result.skipped }
  } catch (error) {
    if (error instanceof SimulatorError && error.uncertain) state.customers[customer.id].safety_hold = true
    await saveState(state)
    await recordResult(customer, 'loan_application', error, error.uncertain ? 'unknown' : 'failed')
    return { action: 'loan_application', outcome: error.uncertain ? 'unknown' : 'failed', reason: cleanError(error) }
  }
}

async function recordResult(customer, action, result, outcome) {
  await appendRun({
    at: isoNow(),
    customer_id: customer.id,
    persona_type: customer.persona.profile_type,
    action,
    outcome,
    request_id: result?.requestId ?? null,
    error_code: result instanceof Error ? cleanError(result) : result?.errorCode ?? null,
  })
}

function weeklySlot(customer, action, index, weekDate) {
  const preferredDays = customer.persona.preferred_weekdays?.length ? customer.persona.preferred_weekdays : [weekdayNumber()]
  const hours = customer.persona.preferred_hours?.length ? customer.persona.preferred_hours : [12]
  const totalTarget = Object.values(customer.persona.weekly_targets ?? {}).reduce((sum, value) => sum + value, 0)
  const activeCount = Math.min(preferredDays.length, Math.max(totalTarget ? 1 : 0, customer.persona.active_days_per_week ?? preferredDays.length))
  const activeDays = [...preferredDays]
    .sort((left, right) => hashInt(`${customer.id}:${weekDate}:active:${left}`) - hashInt(`${customer.id}:${weekDate}:active:${right}`))
    .slice(0, activeCount)
  const days = activeDays.length ? activeDays : preferredDays
  const sessions = Math.max(1, customer.persona.sessions_per_active_day ?? 1)
  const seed = `${customer.id}:${weekDate}:${action}:${index}`
  const weekday = days[seededInteger(0, days.length - 1, `${seed}:day`)]
  const session = index % sessions
  const hour = hours[session % hours.length]
  const minute = seededInteger(0, 59, `${seed}:minute`)
  const jitter = customer.persona.timing_jitter_minutes ?? 0
  const jitterOffset = seededInteger(-jitter, jitter, `${seed}:jitter`)
  const minuteOfWeek = ((weekday - 1) * 1440) + hour * 60 + minute + jitterOffset
  const weekStartDate = new Date(`${weekDate}T00:00:00+09:00`)
  return new Date(weekStartDate.getTime() + minuteOfWeek * 60_000)
}

function scheduledAction(customer, state, now = new Date()) {
  const week = weekStart(now)
  const entry = state.customers[customer.id] ?? {}
  const counts = entry.weekly_actions?.[week] ?? {}
  const targets = customer.persona.weekly_targets ?? {}
  for (const action of WEEK_ACTIONS) {
    const target = targets[action] ?? 0
    const completed = counts[action] ?? 0
    for (let index = completed; index < target; index += 1) {
      const due = weeklySlot(customer, action, index, week)
      const slot = `${week}:${action}:${index}`
      const attemptedAt = entry.scheduled_attempts?.[slot]
      const attemptedToday = attemptedAt && dateKey(new Date(attemptedAt)) === dateKey(now)
      if (due <= now && !attemptedToday) return { action, slot }
    }
  }
  return null
}

function fundingPeriodAt(customer, date = new Date()) {
  const funding = customer.persona.funding
  if (!funding) return null
  const parts = intlParts(date)
  if (funding.mode === 'monthly') {
    return Number(parts.day) >= Number(funding.day_of_month ?? 1) ? `${parts.year}-${parts.month}` : null
  }
  if (funding.mode === 'weekly') {
    return weekdayNumber(date) >= Number(funding.weekday ?? 1) ? weekStart(date) : null
  }
  return null
}

function fundingDue(customer, state, now = new Date()) {
  const funding = customer.persona.funding
  const entry = state.customers[customer.id] ?? {}
  if (!funding || !entry.last_funding_at) return false
  const currentDate = dateKey(now)
  const parts = intlParts(now)
  const last = new Date(entry.last_funding_at)
  const lastParts = intlParts(last)
  const hour = customer.persona.preferred_hours?.[0] ?? 12
  if (Number(parts.hour) < hour) return false
  if (funding.mode === 'monthly') {
    const period = `${parts.year}-${parts.month}`
    const lastPeriod = Object.hasOwn(entry, 'last_funding_period')
      ? entry.last_funding_period
      : `${lastParts.year}-${lastParts.month}`
    return Number(parts.day) >= Number(funding.day_of_month ?? 1) && lastPeriod !== period
  }
  if (funding.mode === 'weekly') {
    const period = weekStart(now)
    const lastPeriod = Object.hasOwn(entry, 'last_funding_period')
      ? entry.last_funding_period
      : weekStart(last)
    const fundingDay = Number(funding.weekday ?? 1)
    return weekdayNumber(now) >= fundingDay && lastPeriod !== period
  }
  const interval = Number(funding.interval_days ?? 30)
  return now.getTime() - last.getTime() >= interval * 86_400_000
}

async function maybeFund(page, baseUrl, customer, state) {
  if (!fundingDue(customer, state)) return null
  const amount = customer.persona.funding?.amount ?? 0
  if (!amount) return null
  try {
    const hooks = createWriteHooks(customer, 'funding', state)
    const result = await deposit(page, baseUrl, amount, 'deposit', hooks)
    const entry = state.customers[customer.id]
    entry.last_funding_at = isoNow()
    entry.last_funding_period = fundingPeriodAt(customer)
    if (Number.isInteger(result.body?.balance)) entry.balance = result.body.balance
    delete entry.write_in_flight
    await saveState(state)
    await recordResult(customer, 'funding', result, 'success')
    try {
      entry.balance = await accountBalance(page, baseUrl)
      await saveState(state)
    } catch {
      // 성공 응답 후 화면 갱신이 실패해도 정기 입금을 다시 하지 않습니다.
    }
    return { action: 'funding', outcome: 'success', requestId: result.requestId ?? null }
  } catch (error) {
    await recordResult(customer, 'funding', error, error.uncertain ? 'unknown' : 'failed')
    if (error.uncertain) state.customers[customer.id].safety_hold = true
    await saveState(state)
    return { action: 'funding', outcome: error.uncertain ? 'unknown' : 'failed', reason: cleanError(error) }
  }
}

async function createBrowserPage(browser, baseUrl, deviceId) {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    locale: 'ko-KR',
    timezoneId: TIME_ZONE,
  })
  await context.addCookies([{
    name: 'podobank_device',
    value: deviceId,
    url: baseUrl,
    httpOnly: true,
    secure: baseUrl.startsWith('https:'),
    sameSite: 'Lax',
    expires: Math.floor(Date.now() / 1000) + 365 * 24 * 60 * 60,
  }])
  const page = await context.newPage()
  page.setDefaultTimeout(15_000)
  return { context, page }
}

async function closeSession(page, baseUrl, customer, state) {
  await page.goto(routeUrl(baseUrl, '/me'))
  await page.getByRole('heading', { name: '내 정보', exact: true }).waitFor({ timeout: 15_000 })
  const result = await submitAndWait(page, '/auth/logout', () =>
    page.getByRole('button', { name: '로그아웃', exact: true }).click(),
  )
  await page.getByRole('heading', { name: '포도뱅크 시작하기', exact: true }).waitFor({ timeout: 15_000 })
  state.customers[customer.id].session_status = 'closed'
  state.customers[customer.id].last_seen_at = isoNow()
  await saveState(state)
  await recordResult(customer, 'logout', result, 'success')
}

async function closeSessionSafely(page, baseUrl, customer, state) {
  try {
    await closeSession(page, baseUrl, customer, state)
  } catch (error) {
    state.customers[customer.id].session_status = 'unknown'
    await saveState(state)
    await recordResult(customer, 'logout', error, 'failed')
  }
}

async function runOne(customer, customers, options, baseUrl, state, browser, behavior = false) {
  return withCustomerLock(customer.id, async () => {
    let context
    let page
    try {
      const existing = state.customers[customer.id] ?? {}
      existing.device_id ??= randomUUID()
      state.customers[customer.id] = existing
      await saveState(state)
      const created = await createBrowserPage(browser, baseUrl, existing.device_id)
      context = created.context
      page = created.page
      const entry = await initializeCustomer(page, baseUrl, customer, await simulatorPassword(customer.id), state)
      const actions = []
      const funding = await maybeFund(page, baseUrl, customer, state)
      if (funding) actions.push(funding)
      const loan = await runLoanPlan(page, baseUrl, customer, state)
      if (loan) actions.push(loan)
      if (behavior) {
        const scheduled = options.watch ? scheduledAction(customer, state) : null
        if (options.watch && !scheduled && !funding && !loan) {
          await closeSessionSafely(page, baseUrl, customer, state)
          return { customer_id: customer.id, persona_type: customer.persona.profile_type, outcome: 'idle' }
        }
        if (options.watch && scheduled) {
          entry.scheduled_attempts ??= {}
          entry.scheduled_attempts[scheduled.slot] = isoNow()
          await saveState(state)
        }
        const result = await runBehavior(page, baseUrl, customer, customers, state, scheduled?.action ?? null)
        if (result.action || result.reason) actions.push(result)
      }
      await closeSessionSafely(page, baseUrl, customer, state)
      return { customer_id: customer.id, persona_type: customer.persona.profile_type, outcome: 'success', actions }
    } catch (error) {
      if (error instanceof SimulatorError && error.uncertain) {
        state.customers[customer.id] ??= {}
        state.customers[customer.id].safety_hold = true
        await saveState(state)
      }
      const code = cleanError(error)
      await recordResult(customer, 'session', error, error.uncertain ? 'unknown' : 'failed')
      return { customer_id: customer.id, persona_type: customer.persona.profile_type, outcome: error.uncertain ? 'unknown' : 'failed', error_code: code }
    } finally {
      if (page && state.customers[customer.id]?.session_status === 'authenticated') {
        await closeSessionSafely(page, baseUrl, customer, state)
      }
      if (context) await context.close().catch(() => {})
    }
  })
}

function outputSummary(value) {
  process.stdout.write(`${JSON.stringify(value)}\n`)
}

function dryRun(customers, baseUrl) {
  for (const customer of customers) {
    outputSummary({
      customer_id: customer.id,
      persona_type: customer.persona.profile_type,
      lifecycle: customer.persona.lifecycle,
      target: baseUrl,
      weekly_targets: customer.persona.weekly_targets,
      initial_funding: customer.onboarding?.first_deposit_amount ?? customer.persona.initial_funding_amount ?? 0,
    })
  }
}

function drawCustomers(customers, options, state) {
  const eligible = customers.filter((customer) => {
    const entry = state.customers[customer.id] ?? {}
    return !entry.safety_hold && !entry.write_in_flight && !entry.credentials_rejected
      && !(entry.login_retry_after && Date.now() < entry.login_retry_after)
  })
  return selectActiveCustomers(eligible, Math.min(options.concurrency, options.limit ?? options.concurrency))
}


async function runOnce(customers, allCustomers, options, baseUrl, state, browser) {
  // 송금 상대가 가입할 수 있도록 첫 초기화가 모두 끝난 다음 행동을 실행합니다.
  const initialized = await runBatch(customers, (customer) =>
    runOne(customer, allCustomers, options, baseUrl, state, browser, false))
  for (const result of initialized) outputSummary(result)
  const ready = customers.filter((_, index) => initialized[index].outcome === 'success')
  const results = await runBatch(ready, (customer) =>
    runOne(customer, allCustomers, options, baseUrl, state, browser, true))
  for (const result of results) outputSummary(result)
}

async function watch(customers, allCustomers, options, baseUrl, state, browser) {
  process.stdout.write(`Playwright persona scheduler started (${customers.length} candidates, concurrency ${options.concurrency}, ${TIME_ZONE})\n`)
  const tick = async () => {
    const due = customers.filter((customer) => {
      const entry = state.customers[customer.id] ?? {}
      return !entry.initialized || scheduledAction(customer, state) || fundingDue(customer, state)
    })
    const selected = drawCustomers(due, options, state)
    const results = await runBatch(selected, (customer) =>
      runOne(customer, allCustomers, options, baseUrl, state, browser, true))
    for (const result of results) {
      if (result.outcome !== 'idle') outputSummary(result)
    }
  }
  // 이전 접속이 모두 끝난 뒤 다음 확인을 예약해 실행 묶음이 겹치지 않습니다.
  while (true) {
    await tick()
    await new Promise((resolve) => setTimeout(resolve, options.pollMs))
  }
}

async function main() {
  let options
  try {
    options = parseArgs(process.argv.slice(2))
    if (options.help) {
      process.stdout.write(`${usage()}\n`)
      return
    }
    const { customers, allCustomers } = await loadPersonas()
    const selected = selectCustomers(customers, options)
    const baseUrl = getBaseUrl(options)
    const state = await loadState()
    const drawn = options.watch ? null : drawCustomers(selected, options, state)
    if (options.dryRun) {
      outputSummary({ candidate_count: selected.length, selected_count: drawn.length, concurrency: options.concurrency })
      dryRun(drawn, baseUrl)
      return
    }
    if (!options.watch && !drawn.length) {
      outputSummary({ outcome: 'idle', reason: 'no_active_personas' })
      return
    }
    const { chromium } = await import('playwright')
    const browser = await chromium.launch({ headless: !options.headed })
    try {
      if (options.watch) await watch(selected, allCustomers, options, baseUrl, state, browser)
      else await runOnce(drawn, allCustomers, options, baseUrl, state, browser)
    } finally {
      await browser.close()
    }
  } catch (error) {
    process.stderr.write(`simulator error: ${cleanError(error)}\n`)
    process.stderr.write(`${usage()}\n`)
    process.exitCode = 1
  }
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

await main()
