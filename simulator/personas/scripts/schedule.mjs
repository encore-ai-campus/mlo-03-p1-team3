import { validatePlan } from './plan.mjs'

export function dueSessions(profiles, rows, state, now, limit) {
  if (!Number.isSafeInteger(limit) || limit < 1) throw Error('invalid_session_limit')
  const sessions = validatePlan(profiles, rows)
  return sessions.filter(group => Date.parse(group[0].planned_at) <= now
    && group.some(row => !state.plans?.[row.plan_id]))
    .slice(0, limit).flat()
}
