import { test, expect, type APIRequestContext } from '@playwright/test'

const BASE = 'https://gridpull.com/api'

async function devLogin(req: APIRequestContext): Promise<string> {
  const r = await req.post(`${BASE}/auth/dev-login`, {
    data: { email: 'martin.mashalov@gmail.com', secret: 'gridpull-dev-bypass-2026' },
  })
  expect(r.status(), `dev-login HTTP: ${r.status()}`).toBe(200)
  const body = await r.json()
  expect(body.access_token, 'dev-login missing access_token').toBeTruthy()
  return body.access_token
}

let TOKEN = ''
test.beforeAll(async ({ request }) => { TOKEN = await devLogin(request) })

function auth() { return { Authorization: `Bearer ${TOKEN}` } }

// GET endpoints that should respond 2xx and return JSON objects for the dev-login user.
const GET_ENDPOINTS: { path: string; must?: string[]; allow404?: boolean; note?: string }[] = [
  { path: '/users/me',                    must: ['email', 'id'] },
  { path: '/users/default-fields' },
  { path: '/payments/subscription',       must: ['tier'] },
  { path: '/payments/saved-card' },
  { path: '/payments/tiers' },
  { path: '/payments/usage-warning' },
  { path: '/payments/me',                  must: ['balance'] },
  { path: '/users/field-presets' },
  { path: '/ingest/address',              must: ['address'] },
  { path: '/ingest/inbox' },
  { path: '/documents/history' },
  { path: '/pipelines/',                  must: ['pipelines'] },
  { path: '/pipelines/connections' },
  { path: '/proposals/agency-info',       must: ['success'] },
]

for (const e of GET_ENDPOINTS) {
  test(`GET ${e.path} -> 2xx`, async ({ request }) => {
    const r = await request.get(`${BASE}${e.path}`, { headers: auth() })
    const bodyText = await r.text().catch(() => '')
    if (e.allow404 && r.status() === 404) return
    expect(r.status(), `GET ${e.path} body=${bodyText.slice(0, 300)}`).toBeLessThan(400)
    // JSON must parse
    const body = (() => { try { return JSON.parse(bodyText) } catch { return null } })()
    expect(body, `GET ${e.path} non-JSON body: ${bodyText.slice(0, 200)}`).not.toBeNull()
    for (const key of e.must ?? []) {
      expect(body, `GET ${e.path} missing key "${key}" in body: ${JSON.stringify(body).slice(0, 300)}`).toHaveProperty(key)
    }
  })
}

// Auth gate: the same endpoints should reject un-authed calls with 401/403.
const AUTH_GATED = ['/users/me', '/payments/subscription', '/ingest/address', '/pipelines/']
for (const p of AUTH_GATED) {
  test(`GET ${p} without auth -> 401/403`, async ({ request }) => {
    const r = await request.get(`${BASE}${p}`)
    expect([401, 403]).toContain(r.status())
  })
}

// 404 for unknown routes should be actual 404 (not silent SPA fallthrough on /api)
test('unknown /api route returns 404', async ({ request }) => {
  const r = await request.get(`${BASE}/does-not-exist-xyz`, { headers: auth() })
  expect(r.status()).toBe(404)
})

// Proposals PUT: non-empty content + no logo -> 200 + success
test('PUT /proposals/agency-info (content only) succeeds', async ({ request }) => {
  const r = await request.put(`${BASE}/proposals/agency-info`, {
    headers: auth(),
    multipart: { content: `audit-${Date.now()}` },
  })
  const body = await r.text()
  expect(r.status(), `body=${body.slice(0, 300)}`).toBe(200)
  expect(JSON.parse(body).success).toBe(true)
})

// Negative: proposals generate without documents should 4xx (not 500)
test('POST /proposals/generate with no documents -> 4xx (not 5xx)', async ({ request }) => {
  const r = await request.post(`${BASE}/proposals/generate`, {
    headers: auth(),
    multipart: { lob: 'commercial_general_liability' },
  })
  expect(r.status()).toBeLessThan(500)
  expect(r.status()).toBeGreaterThanOrEqual(400)
})

// Ingest address must be stable (idempotent): two GETs return the same address
test('GET /ingest/address is idempotent', async ({ request }) => {
  const a = await (await request.get(`${BASE}/ingest/address`, { headers: auth() })).json()
  const b = await (await request.get(`${BASE}/ingest/address`, { headers: auth() })).json()
  expect(a.address).toBeTruthy()
  expect(a.address).toBe(b.address)
})

// Usage counters must be consistent across the three endpoints that report them.
// If they diverge, it means the cache and DB are out of sync — a real bug.
test('usage counters agree across /users/me, /payments/subscription, /payments/usage-warning', async ({ request }) => {
  const me = await (await request.get(`${BASE}/users/me`, { headers: auth() })).json()
  const sub = await (await request.get(`${BASE}/payments/subscription`, { headers: auth() })).json()
  const warn = await (await request.get(`${BASE}/payments/usage-warning`, { headers: auth() })).json()
  expect(sub.pages_used, `sub.pages_used=${sub.pages_used} me.pages_used_this_period=${me.pages_used_this_period}`).toBe(me.pages_used_this_period)
  expect(warn.pages_used, `warn.pages_used=${warn.pages_used} sub.pages_used=${sub.pages_used}`).toBe(sub.pages_used)
  expect(sub.pages_limit, 'pages_limit divergence').toBe(warn.pages_limit)
  expect(sub.tier?.name, 'tier divergence').toBe(warn.tier)
})

// A proposal must charge exactly 5 pages on success. We skip if the user has no Papyra link,
// but the delta must be exactly PROPOSAL_PAGE_COST when a proposal completes.
test('POST /proposals/generate charges exactly 5 pages on success', async ({ request }) => {
  const before = await (await request.get(`${BASE}/payments/subscription`, { headers: auth() })).json()
  const beforePages = before.pages_used

  // Minimal 1-page PDF bytes (standard stub)
  const PDF_STUB = Buffer.from(
    '255044462d312e340a25e2e3cfd30a312030206f626a0a3c3c2f54797065202f436174616c6f672f5061676573203220302052203e3e0a656e646f626a0a322030206f626a0a3c3c2f54797065202f50616765732f436f756e742031202f4b696473205b33203020525d3e3e0a656e646f626a0a332030206f626a0a3c3c2f54797065202f506167652f506172656e7420322030205220',
    'hex',
  )

  const form = new FormData()
  form.append('lob', 'commercial_general_liability')
  form.append('documents', new Blob([PDF_STUB], { type: 'application/pdf' }), 'stub.pdf')

  const r = await request.post(`${BASE}/proposals/generate`, {
    headers: auth(),
    multipart: {
      lob: 'commercial_general_liability',
      documents: { name: 'stub.pdf', mimeType: 'application/pdf', buffer: PDF_STUB },
    },
  })
  const status = r.status()
  const body = await r.text()

  // If Papyra returns an error (e.g., the stub PDF isn't a valid quote), we still
  // want to make sure the user was NOT charged. Delta must be 0 on failure, 5 on success.
  const after = await (await request.get(`${BASE}/payments/subscription`, { headers: auth() })).json()
  const delta = after.pages_used - beforePages

  if (status === 200) {
    expect(delta, `Successful proposal should charge 5 pages, charged ${delta}. Body: ${body.slice(0, 200)}`).toBe(5)
  } else {
    expect(delta, `Failed proposal (status ${status}) should charge 0 pages, charged ${delta}. Body: ${body.slice(0, 200)}`).toBe(0)
  }
})

// ── Form filling validation gates ────────────────────────────────────────────
// These must reject malformed inputs BEFORE doing any expensive LLM work,
// otherwise a user could burn pages on a bad request.

test('POST /form-filling/fill without target_form -> 4xx', async ({ request }) => {
  // source_files only; FastAPI should 422 (missing required param)
  const PDF = Buffer.from('%PDF-1.4\n%EOF\n')
  const r = await request.post(`${BASE}/form-filling/fill`, {
    headers: auth(),
    multipart: {
      source_files: { name: 's.pdf', mimeType: 'application/pdf', buffer: PDF },
    },
  })
  expect(r.status(), `status=${r.status()}`).toBeGreaterThanOrEqual(400)
  expect(r.status()).toBeLessThan(500)
})

test('POST /form-filling/fill with non-PDF target -> 400', async ({ request }) => {
  const PDF = Buffer.from('%PDF-1.4\n%EOF\n')
  const r = await request.post(`${BASE}/form-filling/fill`, {
    headers: auth(),
    multipart: {
      target_form: { name: 'form.txt', mimeType: 'text/plain', buffer: Buffer.from('not a pdf') },
      source_files: { name: 's.pdf', mimeType: 'application/pdf', buffer: PDF },
    },
  })
  // Card-gate (402) comes before the PDF check, so accept either
  expect([400, 402, 413]).toContain(r.status())
})

test('POST /form-filling/fill with empty target -> 400', async ({ request }) => {
  const r = await request.post(`${BASE}/form-filling/fill`, {
    headers: auth(),
    multipart: {
      target_form: { name: 'form.pdf', mimeType: 'application/pdf', buffer: Buffer.alloc(0) },
      source_files: { name: 's.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF') },
    },
  })
  expect([400, 402]).toContain(r.status())
})

// ── Schedules / extraction validation ────────────────────────────────────────

test('POST /documents/extract with no files -> 4xx', async ({ request }) => {
  // Use a form body missing the 'files' array → FastAPI 422
  const r = await request.post(`${BASE}/documents/extract`, {
    headers: auth(),
    multipart: {
      fields: JSON.stringify([{ name: 'foo', description: '' }]),
      format: 'xlsx',
    },
  })
  expect(r.status()).toBeGreaterThanOrEqual(400)
  expect(r.status()).toBeLessThan(500)
})

test('POST /documents/extract with no fields -> 400', async ({ request }) => {
  const PDF = Buffer.from('%PDF-1.4\n%EOF\n')
  const r = await request.post(`${BASE}/documents/extract`, {
    headers: auth(),
    multipart: {
      files: { name: 'x.pdf', mimeType: 'application/pdf', buffer: PDF },
      fields: '[]',
      format: 'xlsx',
    },
  })
  expect([400, 402]).toContain(r.status())
})

test('POST /documents/spreadsheet-headers rejects non-spreadsheet', async ({ request }) => {
  const r = await request.post(`${BASE}/documents/spreadsheet-headers`, {
    headers: auth(),
    multipart: {
      file: { name: 'x.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF') },
    },
  })
  expect(r.status()).toBe(400)
})

test('GET /documents/history returns array-shaped payload', async ({ request }) => {
  const r = await request.get(`${BASE}/documents/history`, { headers: auth() })
  expect(r.status()).toBeLessThan(400)
  const body = await r.json()
  // Must be an object with a jobs (or similar) list, OR directly an array
  const isArr = Array.isArray(body)
  const hasList = !isArr && (Array.isArray(body.jobs) || Array.isArray(body.items) || Array.isArray(body.history))
  expect(isArr || hasList, `history shape: ${JSON.stringify(body).slice(0, 200)}`).toBe(true)
})

// ── Inbox shape ──────────────────────────────────────────────────────────────

test('GET /ingest/inbox returns {groups, total_documents}', async ({ request }) => {
  const r = await request.get(`${BASE}/ingest/inbox`, { headers: auth() })
  expect(r.status()).toBeLessThan(400)
  const body = await r.json()
  expect(body).toHaveProperty('groups')
  expect(Array.isArray(body.groups)).toBe(true)
  expect(body).toHaveProperty('total_documents')
  expect(typeof body.total_documents).toBe('number')
})

test('POST /ingest/inbox/extract with no documents -> 400', async ({ request }) => {
  const r = await request.post(`${BASE}/ingest/inbox/extract`, {
    headers: { ...auth(), 'Content-Type': 'application/json' },
    data: { document_ids: [], fields: [{ name: 'x', description: '' }] },
  })
  expect([400, 422]).toContain(r.status())
})

test('POST /ingest/inbox/extract with no fields -> 400', async ({ request }) => {
  const r = await request.post(`${BASE}/ingest/inbox/extract`, {
    headers: { ...auth(), 'Content-Type': 'application/json' },
    data: { document_ids: ['fake-id'], fields: [] },
  })
  expect([400, 422]).toContain(r.status())
})

test('ingest address is a valid email format', async ({ request }) => {
  const r = await request.get(`${BASE}/ingest/address`, { headers: auth() })
  const body = await r.json()
  expect(body.address).toMatch(/^[^\s@]+@[^\s@]+\.[^\s@]+$/)
})

// ── Pipelines ────────────────────────────────────────────────────────────────

test('GET /pipelines/ returns {pipelines: [...]}', async ({ request }) => {
  const r = await request.get(`${BASE}/pipelines/`, { headers: auth() })
  expect(r.status()).toBeLessThan(400)
  const body = await r.json()
  expect(body).toHaveProperty('pipelines')
  expect(Array.isArray(body.pipelines)).toBe(true)
})

test('GET /pipelines/connections returns object shape', async ({ request }) => {
  const r = await request.get(`${BASE}/pipelines/connections`, { headers: auth() })
  expect(r.status()).toBeLessThan(400)
  const body = await r.json()
  expect(typeof body).toBe('object')
  expect(body).not.toBeNull()
})

test('POST /pipelines/ with missing name -> 400/403', async ({ request }) => {
  const r = await request.post(`${BASE}/pipelines/`, {
    headers: { ...auth(), 'Content-Type': 'application/json' },
    data: {
      name: '',
      source_type: 'google_drive',
      dest_format: 'xlsx',
      fields: [{ name: 'x', description: '' }],
    },
  })
  // 403 if tier doesn't include pipelines, 400 if validation fails
  expect([400, 403, 422]).toContain(r.status())
})

test('POST /pipelines/ with invalid source_type -> 400/403', async ({ request }) => {
  const r = await request.post(`${BASE}/pipelines/`, {
    headers: { ...auth(), 'Content-Type': 'application/json' },
    data: {
      name: 'Test',
      source_type: 'bogus_source',
      dest_format: 'xlsx',
      fields: [{ name: 'x', description: '' }],
    },
  })
  expect([400, 403, 422]).toContain(r.status())
})

// ── Proposals validation ─────────────────────────────────────────────────────

test('POST /proposals/generate without lob -> 4xx', async ({ request }) => {
  const r = await request.post(`${BASE}/proposals/generate`, {
    headers: auth(),
    multipart: {
      documents: { name: 'x.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF') },
    },
  })
  expect(r.status()).toBeGreaterThanOrEqual(400)
  expect(r.status()).toBeLessThan(500)
})

test('PUT /proposals/agency-info without content -> 4xx', async ({ request }) => {
  const r = await request.put(`${BASE}/proposals/agency-info`, {
    headers: auth(),
    multipart: {},
  })
  expect(r.status()).toBeGreaterThanOrEqual(400)
  expect(r.status()).toBeLessThan(500)
})

// ── Cache vs DB consistency: after a 4xx, usage must not increment ───────────

test('rejected extraction does NOT increment pages_used', async ({ request }) => {
  const before = await (await request.get(`${BASE}/payments/subscription`, { headers: auth() })).json()
  const beforePages = before.pages_used

  // Send a request guaranteed to fail validation (no fields, no files)
  const r = await request.post(`${BASE}/documents/extract`, {
    headers: auth(),
    multipart: { fields: '[]', format: 'xlsx' },
  })
  expect(r.status()).toBeGreaterThanOrEqual(400)

  // Wait a beat for any async cache invalidation
  await new Promise(res => setTimeout(res, 250))
  const after = await (await request.get(`${BASE}/payments/subscription`, { headers: auth() })).json()
  expect(after.pages_used - beforePages, `Rejected extraction must not charge — delta=${after.pages_used - beforePages}`).toBe(0)
})

test('rejected form-fill does NOT increment pages_used', async ({ request }) => {
  const before = await (await request.get(`${BASE}/payments/subscription`, { headers: auth() })).json()
  const beforePages = before.pages_used

  const r = await request.post(`${BASE}/form-filling/fill`, {
    headers: auth(),
    multipart: {
      target_form: { name: 'x.txt', mimeType: 'text/plain', buffer: Buffer.from('nope') },
      source_files: { name: 's.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF') },
    },
  })
  expect(r.status()).toBeGreaterThanOrEqual(400)

  await new Promise(res => setTimeout(res, 250))
  const after = await (await request.get(`${BASE}/payments/subscription`, { headers: auth() })).json()
  expect(after.pages_used - beforePages, `Rejected form-fill must not charge — delta=${after.pages_used - beforePages}`).toBe(0)
})
