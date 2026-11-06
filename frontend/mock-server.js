import { createServer } from 'node:http'
import { randomUUID } from 'node:crypto'

const PORT = 8001
const DEMO_PHONE = '01000000000'
const SESSION_COOKIE = 'podobank_session'
const sessions = new Map()

const state = {
  balance: 2_523_000,
  nextTransactionId: 4,
  loans: [],
  ledger: [
    {
      transaction_id: 'mock-tx-003',
      entry_type: 'deposit',
      amount: 600_000,
      balance_after: 2_523_000,
      created_at: minutesAgo(12),
    },
    {
      transaction_id: 'mock-tx-002',
      entry_type: 'card_payment',
      amount: -27_000,
      balance_after: 1_923_000,
      created_at: hoursAgo(3),
    },
    {
      transaction_id: 'mock-tx-001',
      entry_type: 'deposit',
      amount: 1_950_000,
      balance_after: 1_950_000,
      created_at: daysAgo(2),
    },
  ],
}

const demoUser = { name: '김포도', role: 'customer', phone_number: DEMO_PHONE }

const merchants = [
  { id: 'm-001', name: '포도마켓', region: '서울 마포구', category: '마트' },
  { id: 'm-002', name: '작은정원 카페', region: '서울 성동구', category: '카페' },
  { id: 'm-003', name: '오늘의 베이커리', region: '서울 종로구', category: '음식점' },
  { id: 'm-004', name: '동네서점', region: '서울 용산구', category: '문화' },
  { id: 'm-005', name: '푸른문구', region: '서울 마포구', category: '생활' },
]

const loanProducts = [
  {
    code: 'car',
    name: '자동차 대출',
    min_amount: 1_000_000,
    max_amount: 50_000_000,
    amount_step: 1_000_000,
    term_options: [12, 24, 36],
  },
  {
    code: 'jeonse',
    name: '전세 대출',
    min_amount: 1_000_000,
    max_amount: 200_000_000,
    amount_step: 1_000_000,
    term_options: [12, 24, 36],
  },
  {
    code: 'home',
    name: '주택 대출',
    min_amount: 1_000_000,
    max_amount: 600_000_000,
    amount_step: 1_000_000,
    term_options: [12, 24, 36],
  },
]

function minutesAgo(minutes) {
  return new Date(Date.now() - minutes * 60_000).toISOString()
}

function hoursAgo(hours) {
  return new Date(Date.now() - hours * 3_600_000).toISOString()
}

function daysAgo(days) {
  return new Date(Date.now() - days * 86_400_000).toISOString()
}

function readJson(request) {
  return new Promise((resolve, reject) => {
    let raw = ''
    request.setEncoding('utf8')
    request.on('data', (chunk) => {
      raw += chunk
      if (raw.length > 1_000_000) reject(new Error('요청 본문이 너무 큽니다.'))
    })
    request.on('end', () => {
      if (!raw) return resolve({})
      try {
        resolve(JSON.parse(raw))
      } catch {
        reject(new Error('JSON 형식이 올바르지 않습니다.'))
      }
    })
    request.on('error', reject)
  })
}

function sendJson(response, status, body, headers = {}) {
  response.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    ...headers,
  })
  response.end(JSON.stringify(body))
}

function sendError(response, status, code, message, fields = undefined) {
  sendJson(response, status, { code, message, ...(fields ? { fields } : {}) })
}

function sendNoContent(response, headers = {}) {
  response.writeHead(204, headers)
  response.end()
}

function getSessionId(request) {
  const cookies = request.headers.cookie ?? ''
  const cookie = cookies.split(';').map((part) => part.trim()).find((part) => part.startsWith(`${SESSION_COOKIE}=`))
  return cookie?.slice(SESSION_COOKIE.length + 1) ?? null
}

function getUser(request) {
  const sessionId = getSessionId(request)
  return sessionId ? sessions.get(sessionId) : null
}

function startSession(response, user = demoUser) {
  const sessionId = randomUUID()
  sessions.set(sessionId, user)
  response.setHeader(
    'set-cookie',
    `${SESSION_COOKIE}=${sessionId}; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600`,
  )
}

function requireUser(request, response) {
  const user = getUser(request)
  if (!user) {
    sendError(response, 401, 'unauthorized', '로그인이 필요해요.')
    return null
  }
  return user
}

function appendTransaction(entryType, amount) {
  state.balance += amount
  const transaction = {
    transaction_id: `mock-tx-${String(state.nextTransactionId++).padStart(3, '0')}`,
    entry_type: entryType,
    amount,
    balance_after: state.balance,
    created_at: new Date().toISOString(),
  }
  state.ledger.unshift(transaction)
  return transaction
}

function findRecipient(query) {
  if (query === '01000000001' || query === '200-1234-0001') return '이하늘'
  if (query === '01000000002' || query === '200-1234-0002') return '박바다'
  return null
}

function isValidMoney(amount) {
  return Number.isSafeInteger(amount) && amount >= 1 && amount <= 10_000_000
}

function loanDueDate(index) {
  const dueDate = new Date()
  dueDate.setMonth(dueDate.getMonth() + index + 1)
  return dueDate.toISOString().slice(0, 10)
}

function findLoanProduct(code) {
  return loanProducts.find((product) => product.code === code)
}

async function handleRequest(request, response) {
  const url = new URL(request.url, 'http://127.0.0.1')
  const path = url.pathname.replace(/^\/api\/v1/, '') || '/'
  const method = request.method ?? 'GET'
  let body = {}

  if (method !== 'GET' && method !== 'HEAD') {
    try {
      body = await readJson(request)
    } catch (error) {
      return sendError(response, 400, 'invalid_json', error.message)
    }
  }

  if (path === '/health' && method === 'GET') {
    return sendJson(response, 200, { status: 'ok', mode: 'mock' })
  }

  if (path === '/auth/login' && method === 'POST') {
    if (body.phone_number !== DEMO_PHONE || !body.password) {
      return sendError(response, 401, 'invalid_credentials', '시연 계정 정보를 확인해 주세요.')
    }
    startSession(response)
    return sendJson(response, 200, { status: 'authenticated' })
  }

  if (path === '/auth/signup' && method === 'POST') {
    if (!body.name || !body.phone_number) {
      return sendError(response, 422, 'validation_error', '필수 정보를 입력해 주세요.', {
        name: !body.name,
        phone_number: !body.phone_number,
      })
    }
    startSession(response, { name: body.name, role: 'customer', phone_number: body.phone_number })
    return sendJson(response, 201, { status: 'authenticated' })
  }

  if (path === '/auth/kakao/start' && method === 'POST') {
    return sendJson(response, 200, {
      authorization_url: 'http://localhost:5173/auth/kakao/callback?code=mock-code&state=mock-state',
    })
  }

  if (path === '/auth/kakao/login' && method === 'POST') {
    if (body.code !== 'mock-code' || body.state !== 'mock-state') {
      return sendError(response, 400, 'invalid_state', '시연용 카카오 인증 정보가 올바르지 않아요.')
    }
    startSession(response)
    return sendJson(response, 200, { status: 'authenticated' })
  }

  if (path === '/auth/kakao/signup' && method === 'POST') {
    startSession(response, { ...demoUser, phone_number: body.phone_number ?? DEMO_PHONE })
    return sendJson(response, 201, { status: 'authenticated' })
  }

  if (path === '/auth/logout' && method === 'POST') {
    const sessionId = getSessionId(request)
    if (sessionId) sessions.delete(sessionId)
    return sendNoContent(response, {
      'set-cookie': `${SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`,
    })
  }

  if (path === '/auth/me' && method === 'GET') {
    const user = requireUser(request, response)
    if (!user) return
    return sendJson(response, 200, { name: user.name, role: user.role })
  }

  const user = requireUser(request, response)
  if (!user) return

  if (path === '/accounts/me' && method === 'GET') {
    return sendJson(response, 200, { account_number: '100-1234-5678', balance: state.balance })
  }

  if (path === '/accounts/me/ledger' && method === 'GET') {
    const requestedLimit = Number(url.searchParams.get('limit') ?? 50)
    const limit = Number.isSafeInteger(requestedLimit) ? Math.max(1, Math.min(100, requestedLimit)) : 50
    return sendJson(response, 200, { items: state.ledger.slice(0, limit) })
  }

  if (path === '/transactions/deposit' && method === 'POST') {
    if (!isValidMoney(body.amount)) return sendError(response, 422, 'validation_error', '1원부터 1,000만 원까지 입금할 수 있어요.')
    const transaction = appendTransaction('deposit', body.amount)
    return sendJson(response, 201, { transaction_id: transaction.transaction_id, balance: state.balance })
  }

  if (path === '/transactions/withdrawal' && method === 'POST') {
    if (!isValidMoney(body.amount)) return sendError(response, 422, 'validation_error', '1원부터 1,000만 원까지 출금할 수 있어요.')
    if (body.amount > state.balance) return sendError(response, 409, 'insufficient_funds', '잔액이 부족해요.')
    const transaction = appendTransaction('withdrawal', -body.amount)
    return sendJson(response, 201, { transaction_id: transaction.transaction_id, balance: state.balance })
  }

  if (path === '/transfers/recipient-lookup' && method === 'POST') {
    const name = findRecipient(body.query)
    if (!name) return sendError(response, 404, 'recipient_not_found', '받는 분을 찾을 수 없어요.')
    return sendJson(response, 200, { name })
  }

  if (path === '/transfers' && method === 'POST') {
    const name = findRecipient(body.recipient)
    if (!name) return sendError(response, 404, 'recipient_not_found', '받는 분을 찾을 수 없어요.')
    if (!isValidMoney(body.amount)) return sendError(response, 422, 'validation_error', '1원부터 1,000만 원까지 보낼 수 있어요.')
    if (body.amount > state.balance) return sendError(response, 409, 'insufficient_funds', '잔액이 부족해요.')
    const transaction = appendTransaction('transfer_out', -body.amount)
    return sendJson(response, 201, { transaction_id: transaction.transaction_id, balance: state.balance })
  }

  if (path === '/cards/me' && method === 'GET') {
    return sendJson(response, 200, { card_last4: '4826' })
  }

  if (path === '/merchants' && method === 'GET') {
    return sendJson(response, 200, merchants)
  }

  if (path === '/cards/payments' && method === 'POST') {
    const merchant = merchants.find((item) => item.id === body.merchant_id)
    if (!merchant) return sendError(response, 404, 'merchant_not_found', '가맹점을 찾을 수 없어요.')
    if (!isValidMoney(body.amount)) return sendError(response, 422, 'validation_error', '1원부터 1,000만 원까지 결제할 수 있어요.')
    if (body.amount > state.balance) return sendError(response, 409, 'insufficient_funds', '잔액이 부족해요.')
    const transaction = appendTransaction('card_payment', -body.amount)
    return sendJson(response, 201, { transaction_id: transaction.transaction_id, balance: state.balance })
  }

  if (path === '/loans/products' && method === 'GET') {
    return sendJson(response, 200, loanProducts)
  }

  if (path === '/loans/me' && method === 'GET') {
    return sendJson(response, 200, state.loans)
  }

  if (path === '/loans/applications' && method === 'POST') {
    if (state.loans.some((loan) => ['pending', 'repaying'].includes(loan.status))) {
      return sendError(response, 409, 'active_loan_exists', '진행 중인 대출이 있어요.')
    }
    const product = findLoanProduct(body.product_code)
    if (!product) return sendError(response, 422, 'validation_error', '대출 상품을 선택해 주세요.')
    if (
      !Number.isSafeInteger(body.amount) ||
      body.amount < product.min_amount ||
      body.amount > product.max_amount ||
      body.amount % product.amount_step !== 0 ||
      !product.term_options.includes(body.term_months)
    ) {
      return sendError(response, 422, 'validation_error', '금액과 기간을 확인해 주세요.')
    }
    const monthlyInstallment = Math.floor(body.amount / body.term_months)
    const loan = {
      application_id: `mock-loan-${state.loans.length + 1}`,
      product_code: product.code,
      status: 'pending',
      principal_amount: body.amount,
      term_months: body.term_months,
      monthly_installment: monthlyInstallment,
      installments: Array.from({ length: body.term_months }, (_, index) => ({
        number: index + 1,
        due_date: loanDueDate(index),
        amount: monthlyInstallment,
        status: 'scheduled',
      })),
    }
    state.loans.unshift(loan)
    return sendJson(response, 201, {
      application_id: loan.application_id,
      status: loan.status,
      monthly_installment: loan.monthly_installment,
    })
  }

  return sendError(response, 404, 'not_found', '요청한 목 API를 찾을 수 없어요.')
}

const server = createServer((request, response) => {
  handleRequest(request, response).catch((error) => {
    console.error(`Mock API error: ${error.message}`)
    if (!response.headersSent) sendError(response, 500, 'mock_server_error', '목 API 서버 오류가 발생했어요.')
    else response.end()
  })
})

server.listen(PORT, '127.0.0.1', () => {
  console.log(`Mock API ready at http://127.0.0.1:${PORT}/api/v1`)
  console.log(`Demo login: ${DEMO_PHONE} / any non-empty password`)
  console.log('Data is stored in memory and resets when this process stops.')
})
