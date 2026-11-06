const BASE_URL = '/api/v1'

export class ApiError extends Error {
  constructor(status, code, message, fields = null) {
    super(message)
    this.status = status
    this.code = code
    // 입력 형식 오류(422 validation_error)일 때 틀린 칸 이름 → 메시지
    this.fields = fields
  }
}

// 응답이 이 시간 안에 오지 않으면 기다리지 않고 끊는다. 버튼이 '하는 중'에서 멈추지 않게 한다.
const TIMEOUT_MS = 15_000
// 돈이 움직이는 요청은 응답을 못 받아도 서버에서는 처리됐을 수 있다. 중복 요청 방지 키가 아직 없어서
// 같은 요청을 바로 다시 보내지 않도록 내역부터 확인하라고 알린다.
const UNSURE_MESSAGE = '응답을 받지 못했어요. 이미 처리됐을 수 있으니 거래내역을 먼저 확인해 주세요.'

// 같은 주소의 GET이 이미 가는 중이면 새로 보내지 않고 그 응답을 함께 쓴다.
// 예: 대출 화면은 계좌 스토어(부채 합계)와 대출 스토어가 둘 다 /loans/me를 읽는다.
const pendingGets = new Map()

// 로그인은 HttpOnly 쿠키라서 토큰을 직접 다루지 않는다. 같은 주소로 요청하면 브라우저가 쿠키를 붙인다.
// moneyMove: 송금·입출금·결제·대출 신청처럼 두 번 처리되면 안 되는 요청
export function request(path, options = {}) {
  if ((options.method ?? 'GET') !== 'GET') return send(path, options)

  const pending = pendingGets.get(path)
  if (pending) return pending
  const promise = send(path, options).finally(() => pendingGets.delete(path))
  pendingGets.set(path, promise)
  return promise
}

async function send(path, { method = 'GET', body, moneyMove = false } = {}) {
  const headers = {}
  if (body) headers['Content-Type'] = 'application/json'

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)

  let response
  let data
  try {
    try {
      response = await fetch(`${BASE_URL}${path}`, {
        method,
        headers,
        credentials: 'same-origin',
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      })
    } catch {
      if (moneyMove) throw new ApiError(0, 'UNSURE_RESULT', UNSURE_MESSAGE)
      if (controller.signal.aborted) {
        throw new ApiError(0, 'TIMEOUT', '응답이 늦어요. 잠시 후 다시 시도해 주세요.')
      }
      throw new ApiError(0, 'NETWORK_ERROR', '서버에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.')
    }

    if (response.status === 204) return null
    data = await response.json().catch(() => null)
  } finally {
    clearTimeout(timer)
  }
  if (!response.ok) {
    throw new ApiError(
      response.status,
      data?.code ?? 'UNKNOWN_ERROR',
      data?.message ?? '문제가 생겼어요. 잠시 후 다시 시도해 주세요.',
      data?.fields ?? null,
    )
  }
  return data
}
