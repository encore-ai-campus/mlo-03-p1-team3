import { spawnSync } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..')
const marker='# podobank-persona-simulator'
const quote=s=>"'"+s.replaceAll("'","'\\''")+"'"
const entry=`*/5 * * * * /bin/bash ${quote(resolve(root,'scripts/run-scheduled.sh'))} ${quote(process.execPath)} >> ${quote(resolve(root,'planner/data/cron.log'))} 2>&1 ${marker}`
if(process.argv.includes('--dry-run')) { console.log(entry); process.exit(0) }
const old=spawnSync('/usr/bin/crontab',['-l'],{encoding:'utf8',timeout:15000})
if(old.error || (old.status!==0 && !old.stderr.includes('no crontab'))) throw Error('cannot_read_existing_crontab')
const lines=old.stdout.split('\n').filter(s=>s.trim() && !s.endsWith(marker))
if(!process.argv.includes('--remove')) { mkdirSync(resolve(root,'planner/data'),{recursive:true});lines.push(entry) }
const result=spawnSync('/usr/bin/crontab',['-'],{input:lines.join('\n')+'\n',encoding:'utf8',timeout:15000})
if(result.error||result.status!==0) throw Error('cannot_install_crontab')
console.log(process.argv.includes('--remove')?'PodoBank cron removed; other entries preserved.':'PodoBank cron installed: every 5 minutes; other entries preserved.')
