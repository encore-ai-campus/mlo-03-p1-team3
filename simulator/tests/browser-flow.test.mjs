import assert from 'node:assert/strict'
import test from 'node:test'
import { EventEmitter } from 'node:events'
import { deviceUuid, responseResult, createBrowserPage, waitForApiReads, apiWait } from '../personas/scripts/run-playwright.mjs'

function request(path) {
  return { method: () => 'GET', url: () => 'http://localhost:8080/api/v1' + path }
}

async function trackedPage() {
  const page = new EventEmitter()
  page.url = () => 'http://localhost:8080/'
  page.setDefaultTimeout = () => {}
  const cookies = []
  const context = { addCookies: async c => cookies.push(...c), newPage: async () => page }
  await createBrowserPage({ newContext: async () => context }, 'http://localhost:8080', 'device-sim-0001')
  return { page, cookies }
}

test('계획의 같은 기기는 안정적인 UUID이며 신규 기기만 다른 UUID입니다', async () => {
  const { cookies } = await trackedPage()
  const primary = deviceUuid('device-sim-0001')
  assert.match(primary, /^[a-f0-9]{8}-[a-f0-9]{4}-5[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/)
  assert.equal(cookies[0].value, primary)
  assert.equal(deviceUuid('device-sim-0001'), primary)
  assert.equal(deviceUuid(primary), primary)
  assert.notEqual(deviceUuid('new-device-sim-0001:2026-11-06'), primary)
})

test('조회 응답 헤더만 도착한 상태에서는 다음 단계로 이동하지 않습니다', async () => {
  const { page } = await trackedPage(), r = request('/accounts/me')
  page.emit('request', r)
  let finished = false
  const waiting = waitForApiReads(page).then(() => { finished = true })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(finished, false)
  page.emit('requestfinished', r)
  await waiting
  assert.equal(finished, true)
})

test('대출 응답 대기는 이전 홈 화면의 같은 URL 응답을 받지 않습니다', async () => {
  const { page } = await trackedPage(), old = request('/loans/me'), fresh = request('/loans/me')
  page.emit('request', old)
  page.url = () => 'http://localhost:8080/loan'
  page.emit('request', fresh)
  page.waitForResponse = async predicate => {
    const wrap = r => ({ request: () => r, url: r.url })
    assert.equal(predicate(wrap(old)), false)
    assert.equal(predicate(wrap(fresh)), true)
    return 'fresh-only'
  }
  assert.equal(await apiWait(page, '/loans/me', 'GET', { documentPath: '/loan' }), 'fresh-only')
})

test('본문 읽기 실패는 null이 아니라 요청 번호를 가진 구체적인 오류입니다', async () => {
  const response = method => ({
    headers: () => ({'x-request-id': 'rid-safe'}), status: () => 200, ok: () => true,
    request: () => ({method: () => method}), json: async () => { throw Error('private raw error') },
  })
  await assert.rejects(responseResult(response('GET')), e => e.code === 'response_body_unavailable' && e.requestId === 'rid-safe' && !e.uncertain && !e.message.includes('private'))
  await assert.rejects(responseResult(response('POST')), e => e.code === 'response_body_unavailable' && e.uncertain)
})
