import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dueSessions } from '../personas/scripts/schedule.mjs'
import { executePlan, validatePlan } from '../personas/scripts/plan.mjs'
const profiles=JSON.parse(readFileSync(new URL('../planner/samples/profiles.json',import.meta.url)))
const rows=readFileSync(new URL('../planner/samples/plan_2026-11-06.jsonl',import.meta.url),'utf8').trim().split('\n').map(JSON.parse)
test('future sessions stay pending and due selection retains complete sessions',()=>{
 assert.deepEqual(dueSessions(profiles,rows,{},0,10),[])
 const picked=dueSessions(profiles,rows,{},Infinity,2)
 assert.equal(new Set(picked.map(r=>r.session_key)).size,2)
 assert.equal(validatePlan(profiles,picked).length,2)
})
test('completed sessions are omitted; partial sessions keep their original identifiers',()=>{
 const first=dueSessions(profiles,rows,{},Infinity,1)
 const state={plans:Object.fromEntries(first.map(r=>[r.plan_id,{outcome:'success'}]))}
 assert.ok(dueSessions(profiles,rows,state,Infinity,1).every(r=>r.session_key!==first[0].session_key))
 delete state.plans[first[1].plan_id]
 assert.deepEqual(dueSessions(profiles,rows,state,Infinity,1),first)
})
test('bootstrap prepares accounts once and retains safety holds on repeated ticks',async()=>{
 const state={customers:{},plans:{}};let prepared=0
 const driver={prepare:async p=>{prepared++;state.customers[p.sim_user_id]={backend_user_id:1,opening_funded:p.opening_balance_krw}},open:()=>assert.fail('bootstrap must not execute sessions')}
 const args={profiles,rows,concurrency:5,state,save:async()=>{},report:async()=>{},driver,prepareOnly:true,reusePrepared:true}
 assert.equal((await executePlan(args)).prepared_users,600)
 await executePlan(args);assert.equal(prepared,600)
 state.customers[profiles[0].sim_user_id].safety_hold=true
 assert.equal((await executePlan(args)).prepared_users,599);assert.equal(prepared,600)
})
