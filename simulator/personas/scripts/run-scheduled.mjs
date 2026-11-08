import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile, rmdir, readdir } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseEnv } from 'node:util'
import { dueSessions } from './schedule.mjs'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const data = resolve(root, 'planner/data')
const json = async path => JSON.parse(await readFile(path, 'utf8'))
const exists = async path => { try { await readFile(path); return true } catch(e) { if(e.code === 'ENOENT') return false; throw e } }
function run(executable, args, env) {
  const r = spawnSync(executable, args, { cwd: root, env, stdio: 'inherit' })
  if (r.error || r.status !== 0) throw Error('scheduled_child_failed')
}
async function main() {
  const settings = parseEnv(await readFile(resolve(root, 'planner/.env'), 'utf8'))
  const env = { ...process.env, ...settings }
  const url = new URL(env.SIMULATOR_BASE_URL)
  if (!['http:', 'https:'].includes(url.protocol) || url.pathname !== '/' || url.search || url.hash || url.username || url.password) throw Error('invalid_SIMULATOR_BASE_URL')
  const base = url.origin
  env.SIMULATOR_BASE_URL = base
  const concurrency = Number(env.SIMULATOR_CONCURRENCY ?? 5)
  const limit = Number(env.SIMULATOR_SESSIONS_PER_TICK ?? 10)
  if (!Number.isSafeInteger(concurrency) || concurrency < 1 || concurrency > 10) throw Error('invalid_concurrency')
  if (!Number.isSafeInteger(limit) || limit < 1) throw Error('invalid_session_limit')
  await mkdir(data, { recursive: true })
  const key = createHash('sha256').update(base).digest('hex').slice(0, 12)
  const lock = resolve(data, `scheduled-${key}.lock`)
  try { await mkdir(lock) } catch (e) {
    if(e.code !== 'EEXIST') throw e
    console.log(JSON.stringify({ phase:'scheduled_skip', reason:'previous_run_locked' })); return
  }
  try {
    const python = env.SIMULATOR_PYTHON ?? 'python3'
    const profilesPath = resolve(data, 'profiles.json')
    if (!await exists(profilesPath)) run(python, ['planner/persona_sim.py', 'init', '--output', data], env)
    const day = new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Seoul', year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())
    const daily = resolve(data, `plan_${day}.jsonl`)
    if (!await exists(daily)) run(python, ['planner/persona_sim.py','plan','--date',day,'--output',data], env)
    const statePath = resolve(data, `execution-${key}.json`)
    const state = await exists(statePath) ? await json(statePath) : {}
    const profiles = await json(profilesPath)
    const args = ['personas/scripts/run-playwright.mjs','--allow-remote','--concurrency',String(concurrency),'--profiles',profilesPath,'--reuse-prepared']
    if (process.argv.includes('--prepare-only')) {
      run(process.execPath,[...args,'--plan',daily,'--prepare-only'],env); return
    }
    // Retain unfinished prior-day sessions after sleep or downtime; never replay recorded writes.
    const files = (await readdir(data)).filter(n => /^plan_\d{4}-\d{2}-\d{2}\.jsonl$/.test(n)).sort()
    const selected = []
    for (const name of files) {
      const rows = (await readFile(resolve(data,name),'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse)
      const batch = dueSessions(profiles,rows,state,Date.now(),limit)
      if (batch.length) { selected.push(...batch); break }
    }
    console.log(JSON.stringify({phase:'scheduled_tick',at:new Date().toISOString(),sessions:new Set(selected.map(r=>r.session_key)).size,rows:selected.length,concurrency}))
    if (!selected.length) return
    const batch = resolve(data,`scheduled-${key}.jsonl`)
    await writeFile(batch,selected.map(r=>JSON.stringify(r)).join('\n')+'\n',{mode:0o600})
    const approval = env.SIMULATOR_APPROVE_LOANS === 'true' ? ['--approve-loans'] : []
    run(process.execPath,[...args,'--plan',batch,...approval],env)
  } finally { await rmdir(lock) }
}
main().catch(e=>{console.error('scheduled simulator: '+(e.message==='scheduled_child_failed'?e.message:'configuration_or_schedule_failed'));process.exitCode=1})
