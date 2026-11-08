import { createHash } from 'node:crypto'

const actualClock = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
})

export const ACTIONS = new Set(['login', 'logout', 'account_view', 'history_view', 'transfer',
  'card_payment', 'deposit', 'withdrawal', 'loan_products', 'loan_view', 'loan_apply', 'loan_approve'])
export const RETRYABLE_READS = new Set(['account_view', 'history_view', 'loan_products', 'loan_view'])
export const WRITES = new Set(['transfer', 'card_payment', 'deposit', 'withdrawal', 'loan_apply', 'loan_approve'])
const CATEGORIES = new Set(['convenience', 'cafe', 'restaurant', 'grocery', 'gas_station', 'pharmacy'])

export function validatePlan(profiles, rows) {
  if (!Array.isArray(profiles) || !profiles.length || !rows.length) throw Error('empty_plan_or_profiles')
  const users = new Map()
  for (const p of profiles) {
    if (!/^sim-\d{4}$/.test(p.sim_user_id) || users.has(p.sim_user_id)
      || !/^P0[1-4]$/.test(p.persona_type) || !/^[2345]0s$/.test(p.age_band)
      || typeof p.is_employed !== 'boolean' || !p.primary_device_id
      || !Number.isSafeInteger(p.opening_balance_krw) || p.opening_balance_krw < 0) throw Error('invalid_profile')
    users.set(p.sim_user_id, p)
  }
  const ids = new Set(), sessions = new Map()
  for (const r of rows) {
    const p = users.get(r.sim_user_id)
    if (!p || p.persona_type !== r.persona_type || !r.plan_id || ids.has(r.plan_id)
      || !r.session_key || !r.planned_at?.endsWith('+09:00') || !Number.isFinite(Date.parse(r.planned_at))
      || !ACTIONS.has(r.action) || r.execution_status !== 'PLANNED' || !r.params || typeof r.params !== 'object') throw Error('invalid_plan_row')
    ids.add(r.plan_id)
    if (WRITES.has(r.action) && r.action !== 'loan_approve') {
      const n = r.action === 'loan_apply' ? r.params.requested_amount_krw : r.params.amount_krw
      if (!Number.isSafeInteger(n) || n <= 0 || (r.action !== 'loan_apply' && n > 10_000_000)) throw Error('invalid_planned_amount')
    }
    if (r.action === 'transfer' && (!users.has(r.params.recipient_sim_user_id)
      || r.params.recipient_sim_user_id === r.sim_user_id)) throw Error('invalid_planned_recipient')
    if (r.action === 'card_payment' && !CATEGORIES.has(r.params.merchant_category)) throw Error('invalid_merchant_category')
    if (r.action === 'loan_apply' && (r.params.selection_strategy !== 'choose_from_live_loan_products'
      || !Number.isSafeInteger(r.params.preferred_term_months) || r.params.preferred_term_months <= 0)) throw Error('invalid_loan_plan')
    if (r.action === 'loan_approve') {
      const application = rows.find(a => a.plan_id === r.params.application_plan_id)
      if (!application || application.action !== 'loan_apply' || application.sim_user_id !== r.sim_user_id
        || application.session_key !== r.session_key || rows.indexOf(application) >= rows.indexOf(r)
        || Date.parse(application.planned_at) > Date.parse(r.planned_at)) throw Error('invalid_loan_approval_plan')
    }
    const group = sessions.get(r.session_key) ?? []
    group.push(r); sessions.set(r.session_key, group)
  }
  for (const group of sessions.values()) {
    group.sort((a, b) => Date.parse(a.planned_at) - Date.parse(b.planned_at))
    if (group[0].action !== 'login' || group.at(-1).action !== 'logout'
      || group.some(r => r.sim_user_id !== group[0].sim_user_id)
      || group.slice(1, -1).some(r => ['login', 'logout'].includes(r.action))
      || typeof group[0].params.sim_device_id !== 'string') throw Error('invalid_plan_session')
  }
  return [...sessions.values()].sort((a, b) => Date.parse(a[0].planned_at) - Date.parse(b[0].planned_at))
}

// Derived IDs are stable. Existing application rows and their fingerprints are unchanged.
export function withLoanApprovals(rows) {
  return rows.flatMap(row => row.action !== 'loan_apply' || rows.some(r => r.action === 'loan_approve' && r.params.application_plan_id === row.plan_id)
    ? [row] : [row, { ...row, plan_id: row.plan_id + '-employee-approval', action: 'loan_approve',
      params: { application_plan_id: row.plan_id }, reason: 'employee_approval_after_application',
      requires: ['authenticated', 'application_created_by_plan'] }])
}

export function toCustomer(profile) {
  const n = Number(profile.sim_user_id.slice(4))
  return {
    id: profile.sim_user_id,
    signup: { name: `가상고객${n}`, phone_number: `019${String(66000000 + n)}`,
      birth_year: 2026 - Number(profile.age_band.slice(0, 2)) - 5,
      gender: n % 2 ? 'male' : 'female', marital_status: n % 3 ? 'single' : 'married',
      is_employed: profile.is_employed },
    persona: { profile_type: profile.persona_type, lifecycle: 'new',
      recipient_customer_ids: profile.known_recipient_sim_ids ?? [] },
  }
}

// Concurrency caps live customers; the complete queue is drained, never sampled.
export async function workerPool(items, concurrency, run) {
  if (!Number.isSafeInteger(concurrency) || concurrency < 1) throw Error('invalid_concurrency')
  let cursor = 0
  const results = new Array(items.length)
  await Promise.all(Array.from({ length: Math.min(items.length, concurrency) }, async () => {
    while (cursor < items.length) {
      const i = cursor++
      results[i] = await run(items[i], i)
    }
  }))
  return results
}

export function fingerprint(row) {
  return createHash('sha256').update(JSON.stringify(row)).digest('hex')
}

export async function executePlan({ profiles, rows, concurrency, state, save, report, driver, retryFailedReads = false, reusePrepared = false, prepareOnly = false }) {
  const sessions = validatePlan(profiles, rows)
  state.customers ??= {}; state.plans ??= {}
  for (const row of rows) {
    const previous = state.plans[row.plan_id]
    if (previous && previous.fingerprint !== fingerprint(row)) throw Error('changed_plan_id_requires_new_plan')
    if (previous?.outcome === 'started' || previous?.outcome === 'unknown') {
      state.customers[row.sim_user_id] ??= {}
      state.customers[row.sim_user_id].safety_hold = true
    }
  }
  const retryIds = new Set(), retrySessions = new Set()
  if (retryFailedReads) {
    for (const row of rows) {
      const previous = state.plans[row.plan_id]
      if (previous?.outcome === 'failed' && RETRYABLE_READS.has(row.action)) {
        await report({ phase: 'retry_read', plan_id: row.plan_id, sim_user_id: row.sim_user_id,
          action: row.action, previous_outcome: previous.outcome, previous_reason: previous.reason })
        retryIds.add(row.plan_id); retrySessions.add(row.session_key)
      }
    }
  }
  await save(state)
  const ready = new Set()
  if (retryFailedReads) {
    // Re-authenticate only when opening an unfinished session. Never signup or fund in this mode.
    for (const profile of profiles) {
      const entry = state.customers[profile.sim_user_id]
      if (entry?.backend_user_id && !entry.safety_hold && !entry.write_in_flight) ready.add(profile.sim_user_id)
    }
  } else {
    await workerPool(profiles, concurrency, async profile => {
      const entry = state.customers[profile.sim_user_id] ??= {}
      if (entry.safety_hold || entry.write_in_flight) return
      if (reusePrepared && entry.backend_user_id && (entry.opening_funded ?? 0) >= profile.opening_balance_krw) {
        ready.add(profile.sim_user_id)
        return
      }
      try {
        await driver.prepare(profile)
        ready.add(profile.sim_user_id)
      } catch (e) {
        await report({ phase: 'prepare', sim_user_id: profile.sim_user_id, outcome: 'failed', error_code: driver.errorCode(e) })
      }
    })
  }
  if (prepareOnly) return { prepared_users: ready.size, planned_users: 0, planned_rows: 0, outcomes: {} }
  const byUser = new Map()
  for (const session of sessions) {
    if (retryFailedReads && !retrySessions.has(session[0].session_key)) continue
    const id = session[0].sim_user_id
    const list = byUser.get(id) ?? []; list.push(session); byUser.set(id, list)
  }
  async function record(row, outcome, result = {}) {
    const entry = { plan_id: row.plan_id, sim_user_id: row.sim_user_id, session_key: row.session_key,
      persona_type: row.persona_type, action: row.action, planned_at: row.planned_at,
      actual_at: actualClock.format(new Date()).replace(' ', 'T') + '+09:00', outcome, request_id: result.requestId ?? null,
      http_status: result.status ?? null, reason: result.reason ?? null, scenario_tag: row.scenario_tag ?? null,
      fingerprint: fingerprint(row),
      ...(row.action === 'loan_apply' && Number.isSafeInteger(result.body?.application_id) ? { application_id: result.body.application_id } : {}),
      ...(row.action === 'loan_approve' && result.applicationId ? { application_id: result.applicationId,
        verification_request_ids: result.verificationRequestIds } : {}) }
    state.plans[row.plan_id] = entry
    await save(state)
    if (outcome !== 'started') await report(entry)
  }
  await workerPool([...byUser.entries()], concurrency, async ([id, groups]) => {
    for (const group of groups) {
      if (!retryFailedReads && group.every(r => state.plans[r.plan_id] && state.plans[r.plan_id].outcome !== 'started')) continue
      let session = null, blocked = !ready.has(id), blockReason = 'customer_not_ready'
      try {
        for (const row of group) {
          const previous = retryIds.has(row.plan_id) ? null : state.plans[row.plan_id]
          // A partially completed session needs a new real login, but completed writes are never replayed.
          if (row.action === 'login' && !blocked) {
            try {
              session = await driver.open(row)
              if (!previous) await record(row, 'success', session.result)
              else if (retryFailedReads) await report({ phase: 'retry_login', sim_user_id: id,
                session_key: row.session_key, request_id: session.result?.requestId, http_status: session.result?.status })
            } catch (e) {
              blocked = true; blockReason = driver.errorCode(e)
              if (!previous) await record(row, 'failed', { reason: blockReason })
            }
            continue
          }
          if (retryFailedReads && !['login', 'logout'].includes(row.action) && !retryIds.has(row.plan_id)) continue
          if (previous) {
            if (row.action === 'logout' && retryFailedReads && session && !blocked) {
              const result = await driver.close(session)
              await report({ phase: 'retry_logout', sim_user_id: id, session_key: row.session_key,
                request_id: result?.requestId, http_status: result?.status })
            }
            continue
          }
          if (blocked) { await record(row, 'skipped', { reason: blockReason }); continue }
          if (state.customers[id].safety_hold) {
            await record(row, 'skipped', { reason: 'manual_review_required' }); continue
          }
          if (WRITES.has(row.action)) await record(row, 'started')
          try {
            const result = row.action === 'logout' ? await driver.close(session) : await driver.perform(row, session, ready)
            await record(row, result.skipped ? 'skipped' : 'success', { ...result, reason: result.skipped })
          } catch (e) {
            if (e.uncertain) { state.customers[id].safety_hold = true; blocked = true; blockReason = 'manual_review_required' }
            await record(row, e.uncertain ? 'unknown' : 'failed', { requestId: e.requestId, status: e.status, reason: driver.errorCode(e) })
          }
        }
      } finally { if (session) await driver.dispose(session) }
    }
  })
  return { prepared_users: ready.size, planned_users: byUser.size, planned_rows: rows.length,
    outcomes: rows.reduce((counts, r) => {
      const k = state.plans[r.plan_id]?.outcome ?? 'pending'; counts[k] = (counts[k] ?? 0) + 1; return counts
    }, {}) }
}
