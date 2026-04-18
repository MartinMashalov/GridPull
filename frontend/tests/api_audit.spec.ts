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
