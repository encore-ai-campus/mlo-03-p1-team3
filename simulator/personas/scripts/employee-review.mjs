import { randomUUID } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import * as util from 'node:util'
import { SimulatorError } from './run-playwright.mjs'

export async function loadEmployeeCredentials(path) {
  if (!util.parseEnv) throw new SimulatorError('employee_env_requires_node_20_12_or_newer')
  let values
  try { values = util.parseEnv(await readFile(path, 'utf8')) }
  catch { throw new SimulatorError('employee_env_missing_or_invalid') }
  const phone = values.EMPLOYEE_PHONE_NUMBER, password = values.EMPLOYEE_PASSWORD
  if (!/^01[0-9]{8,9}$/.test(phone ?? '') || typeof password !== 'string' || password.length < 8 || password.length > 128) {
    throw new SimulatorError('employee_credentials_missing_or_invalid')
  }
  return { phone_number: phone, password }
}

// Other customers may transfer money to this account while approval is running.
export function verifyDisbursement(beforeBalance, priorItems, currentBalance, items, principal) {
  const prior = new Set(priorItems.map(i => i.transaction_id))
  const added = items.filter(i => !prior.has(i.transaction_id))
  const payments = added.filter(i => i.entry_type === 'loan_disbursement' && i.amount === principal)
  const baseline = priorItems[0]?.balance_after ?? beforeBalance
  return payments.length === 1 && currentBalance === items[0]?.balance_after
    && baseline + added.reduce((sum, i) => sum + i.amount, 0) === currentBalance
}

// Each use has its own cookie jar. Never share customer browser cookies or log credentials.
export function makeEmployeeReviewer({ request, base, credentials, report = async () => {} }) {
  async function session(applicationId, { beforePost = async () => {} } = {}) {
    const url = new URL(base)
    const context = await request.newContext({ baseURL: base, timeout: 15000,
      extraHTTPHeaders: { 'X-Client': 'web', 'User-Agent': 'PodoSimulatorEmployee/1.0' },
      storageState: { cookies: [{ name: 'podobank_device', value: randomUUID(), domain: url.hostname,
        path: '/', expires: -1, httpOnly: true, secure: url.protocol === 'https:', sameSite: 'Lax' }], origins: [] } })
    let authenticated = false, posted = false, result
    async function call(path, method, data) {
      const response = await context.fetch('/api/v1' + path, { method, data, maxRedirects: 0, maxRetries: 0 })
      const requestId = response.headers()['x-request-id'] ?? null, status = response.status()
      let body
      try { body = await response.json() }
      catch { throw new SimulatorError('employee_response_body_unavailable', { requestId, status, uncertain: posted }) }
      if (!response.ok()) throw new SimulatorError(`employee_http_${status}`, { requestId, status, uncertain: posted && status >= 500 })
      return { body, status, requestId }
    }
    try {
      await call('/auth/login', 'POST', credentials)
      authenticated = true
      const me = await call('/auth/me', 'GET')
      if (me.body?.role !== 'bank_employee') throw new SimulatorError('employee_role_required')
      if (applicationId === undefined) return { verified: true }
      if (!Number.isSafeInteger(applicationId) || applicationId <= 0) throw new SimulatorError('invalid_loan_application_id')
      await beforePost()
      posted = true
      result = await call(`/admin/loans/${applicationId}/approve`, 'POST')
      if (result.body?.status !== 'repaying') throw new SimulatorError('loan_approval_status_unexpected', { ...result, uncertain: true })
      return result
    } catch (e) {
      if (e instanceof SimulatorError) throw e
      throw new SimulatorError(posted ? 'loan_approval_response_unknown' : 'employee_session_failed', { uncertain: posted })
    } finally {
      try {
        if (authenticated) await call('/auth/logout', 'POST')
      } catch {
        // An acknowledged financial result must not be retried because cleanup failed.
        await report({ phase: 'employee_logout', outcome: 'failed', reason: 'employee_logout_failed' })
      } finally {
        try { await context.dispose() }
        catch { await report({ phase: 'employee_cleanup', outcome: 'failed', reason: 'employee_context_dispose_failed' }) }
      }
    }
  }
  return { verify: () => session(), approve: (id, options) => session(id, options) }
}
