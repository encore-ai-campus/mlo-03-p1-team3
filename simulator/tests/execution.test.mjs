import assert from 'node:assert/strict'
import test from 'node:test'
import { runBatch } from '../personas/scripts/execution.mjs'

test('선택한 사용자들을 동시에 시작하고 다음 사용자를 추가하지 않습니다', async () => {
  const started = []
  const release = []
  const pending = runBatch(['a', 'b', 'c'], (id) => {
    started.push(id)
    return new Promise((resolve) => release.push(() => resolve(id)))
  })
  assert.deepEqual(started, ['a', 'b', 'c'])
  release.forEach((finish) => finish())
  assert.deepEqual(await pending, ['a', 'b', 'c'])
  assert.equal(started.length, 3)
})

test('한 사용자가 실패해도 다른 접속이 끝난 뒤 실패를 전달합니다', async () => {
  let finish
  let finished = false
  const failure = new Error('failed')
  const pending = runBatch(['bad', 'slow'], (id) => {
    if (id === 'bad') throw failure
    return new Promise((resolve) => { finish = () => { finished = true; resolve() } })
  })
  finish()
  await assert.rejects(pending, (error) => error === failure)
  assert.equal(finished, true)
})
