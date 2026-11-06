// crypto.randomUUID는 HTTPS·localhost에서만 있어서 같은 망 IP로 접속한 휴대폰에서도 되게 직접 만든다.
function newIdempotencyKey() {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
  return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-')
}

// 응답을 못 받았을 때 같은 내용으로 다시 보내면 같은 키를 써서 돈이 두 번 움직이지 않게 한다.
export function createIdempotentAttempt() {
  let key = null

  function reset() {
    key = null
  }

  async function run(send) {
    key ??= newIdempotencyKey()
    try {
      const response = await send(key)
      reset()
      return response
    } catch (error) {
      // 연결 실패나 서버 오류는 돈이 움직였을 수 있어 키를 유지한다.
      if (error.status >= 400 && error.status < 500) reset()
      throw error
    }
  }

  return { run, reset }
}
