/*
 * Real end-to-end happy paths against the live gridpull.com API.
 * These tests INTENTIONALLY spend pages + LLM tokens — they prove the
 * full pipeline works, not just 2xx shape.
 */
import { test, expect, type APIRequestContext } from '@playwright/test'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const BASE = 'https://gridpull.com/api'

async function devLogin(req: APIRequestContext): Promise<string> {
  const r = await req.post(`${BASE}/auth/dev-login`, {
    data: { email: 'martin.mashalov@gmail.com', secret: 'gridpull-dev-bypass-2026' },
  })
  expect(r.status(), `dev-login HTTP: ${r.status()}`).toBe(200)
  return (await r.json()).access_token
}

let TOKEN = ''
test.beforeAll(async ({ request }) => { TOKEN = await devLogin(request) })
function auth() { return { Authorization: `Bearer ${TOKEN}` } }

// ── Form-fill happy path ─────────────────────────────────────────────────────
test('Form-fill: GSA SF1449 + invoice → filled PDF + 5 pages charged', async ({ request }) => {
  test.setTimeout(300_000)  // 5 min — LLM form filling can take a while

  const before = await (await request.get(`${BASE}/payments/subscription`, { headers: auth() })).json()
  const beforePages = before.pages_used

  const target = fs.readFileSync(path.join(__dirname, 'fixtures_gsa_sf1449.pdf'))
  const source = fs.readFileSync(path.join(__dirname, 'fixtures_sample_invoice.pdf'))

  const r = await request.post(`${BASE}/form-filling/fill`, {
    headers: auth(),
    multipart: {
      target_form: { name: 'gsa_sf1449.pdf', mimeType: 'application/pdf', buffer: target },
      source_files: { name: 'invoice.pdf', mimeType: 'application/pdf', buffer: source },
    },
    timeout: 300_000,
  })
  const status = r.status()
  const body = await r.body()
  const bodyPreview = body.slice(0, 300).toString('utf8')

  expect(status, `form-fill status=${status} body=${bodyPreview}`).toBe(200)

  // Response must be an actual PDF (starts with %PDF)
  const head = body.slice(0, 4).toString('ascii')
  expect(head, `returned body is not a PDF, got head=${head}`).toBe('%PDF')
  expect(body.length).toBeGreaterThan(1000)

  // Usage must increment by AT LEAST 5 (concurrent pipelines/ingests could add more).
  // The form-fill route only adds 5 — anything beyond came from parallel work.
  const after = await (await request.get(`${BASE}/payments/subscription`, { headers: auth() })).json()
  const delta = after.pages_used - beforePages
  expect(delta, `Form-fill success should charge ≥5 pages (form-fill is 5), charged ${delta}`).toBeGreaterThanOrEqual(5)
})

// ── Schedules extraction happy path ──────────────────────────────────────────
test('Schedules: invoice PDF → queued job → completed → xlsx + usage increments', async ({ request }) => {
  test.setTimeout(300_000)

  const before = await (await request.get(`${BASE}/payments/subscription`, { headers: auth() })).json()
  const beforePages = before.pages_used

  const invoice = fs.readFileSync(path.join(__dirname, 'fixtures_sample_invoice.pdf'))
  const fields = JSON.stringify([
    { name: 'invoice_number', description: 'invoice number' },
    { name: 'total_amount', description: 'total amount billed' },
    { name: 'vendor_name', description: 'vendor or supplier name' },
  ])

  const r = await request.post(`${BASE}/documents/extract`, {
    headers: auth(),
    multipart: {
      files: { name: 'invoice.pdf', mimeType: 'application/pdf', buffer: invoice },
      fields,
      format: 'xlsx',
    },
    timeout: 60_000,
  })

  const status = r.status()
  const body = await r.text()
  expect(status, `extract status=${status} body=${body.slice(0, 300)}`).toBe(200)
  const submit = JSON.parse(body)
  expect(submit.job_id, 'no job_id returned').toBeTruthy()
  expect(submit.status).toBe('queued')

  const jobId = submit.job_id

  // Poll job status until completed/failed (max 3 min)
  let final: any = null
  const deadline = Date.now() + 180_000
  while (Date.now() < deadline) {
    await new Promise(res => setTimeout(res, 2000))
    const jr = await request.get(`${BASE}/documents/job/${jobId}`, { headers: auth() })
    if (jr.status() !== 200) continue
    const j = await jr.json()
    const term = String(j.status || '').toLowerCase()
    if (term === 'complete' || term === 'completed' || term === 'failed' || term === 'error') { final = j; break }
  }
  expect(final, 'job never reached terminal state').not.toBeNull()
  const status = String(final.status || '').toLowerCase()
  expect(['complete', 'completed']).toContain(status)

  // Download the result
  const dl = await request.get(`${BASE}/documents/download/${jobId}`, { headers: auth() })
  expect(dl.status()).toBe(200)
  const xlsx = await dl.body()
  // xlsx files start with PK (ZIP magic)
  expect(xlsx.slice(0, 2).toString('ascii')).toBe('PK')
  expect(xlsx.length).toBeGreaterThan(500)

  // Usage must have incremented by at least 1 (invoice is 1 page)
  const after = await (await request.get(`${BASE}/payments/subscription`, { headers: auth() })).json()
  const delta = after.pages_used - beforePages
  expect(delta, `Extraction should charge ≥1 page, charged ${delta}`).toBeGreaterThanOrEqual(1)
})
