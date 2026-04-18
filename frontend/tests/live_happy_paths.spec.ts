/*
 * Real end-to-end happy paths against the live gridpull.com API.
 * These tests INTENTIONALLY spend pages + LLM tokens — they prove the full
 * pipeline works, not just 2xx shape.
 *
 * Content validation is done via a dev-gated LLM judge endpoint
 * (POST /auth/dev-llm-judge). The judge extracts text from the returned PDF
 * or xlsx and asks an LLM whether it satisfies a natural-language
 * expectation. This replaces brittle length-only / magic-byte checks.
 */
import { test, expect, type APIRequestContext } from '@playwright/test'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const BASE = 'https://gridpull.com/api'
const DEV_SECRET = 'gridpull-dev-bypass-2026'

async function devLogin(req: APIRequestContext): Promise<string> {
  const r = await req.post(`${BASE}/auth/dev-login`, {
    data: { email: 'martin.mashalov@gmail.com', secret: DEV_SECRET },
  })
  expect(r.status(), `dev-login HTTP: ${r.status()}`).toBe(200)
  return (await r.json()).access_token
}

async function resetUsage(req: APIRequestContext, pages = 100) {
  const r = await req.post(`${BASE}/auth/dev-set-usage`, {
    data: {
      secret: DEV_SECRET,
      subscription_tier: 'pro',
      pages_used_this_period: pages,
      overage_pages_this_period: 0,
    },
  })
  expect(r.status(), `dev-set-usage HTTP ${r.status()}`).toBe(200)
}

/**
 * Ask an LLM to judge whether `artifact` satisfies `expectation`.
 * Returns true iff the judge verdicts "pass". On any non-pass verdict the
 * calling test will fail with the judge's own reasoning attached.
 */
async function llmJudge(
  req: APIRequestContext,
  artifact: { name: string; mimeType: string; buffer: Buffer },
  expectation: string,
): Promise<{ pass: boolean; reasoning: string; extractedChars: number }> {
  const r = await req.post(`${BASE}/auth/dev-llm-judge`, {
    multipart: { secret: DEV_SECRET, expectation, file: artifact },
    timeout: 60_000,
  })
  const status = r.status()
  const text = await r.text()
  if (status !== 200) {
    throw new Error(`llm-judge HTTP ${status}: ${text.slice(0, 400)}`)
  }
  const body = JSON.parse(text)
  return {
    pass: body.verdict === 'pass',
    reasoning: String(body.reasoning || ''),
    extractedChars: Number(body.extracted_chars || 0),
  }
}

let TOKEN = ''
test.beforeAll(async ({ request }) => {
  TOKEN = await devLogin(request)
  await resetUsage(request, 100)
})
function auth() { return { Authorization: `Bearer ${TOKEN}` } }

// ── Form-fill happy path ─────────────────────────────────────────────────────
test('Form-fill: GSA SF1449 + invoice → filled PDF + exactly 5 pages charged', async ({ request }) => {
  test.setTimeout(300_000)  // 5 min — LLM form filling can take a while

  // Unconditional reset right before we measure the baseline so concurrency
  // from unrelated tests can't pollute the delta.
  await resetUsage(request, 100)
  await new Promise(res => setTimeout(res, 1500))  // settle multi-worker cache

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
  expect(status, `form-fill status=${status} body=${body.slice(0, 300).toString('utf8')}`).toBe(200)

  // ── Content validation via LLM judge ───────────────────────────────────
  // Expectation: the returned PDF is a filled GSA SF1449 that contains
  // vendor-identifying details pulled from the sample invoice — not blank,
  // not truncated, not the original unfilled form.
  const judgement = await llmJudge(
    request,
    { name: 'filled.pdf', mimeType: 'application/pdf', buffer: Buffer.from(body) },
    'This should be a filled-in US government purchase order / form (GSA SF1449 style) '
    + 'whose fields have been populated with real vendor/invoice data: at minimum an amount/total, '
    + 'a vendor or company name, and an invoice/PO identifier. A blank form, a PDF containing '
    + 'only placeholder text, or a form with no filled values is a FAIL.',
  )
  expect(
    judgement.pass,
    `LLM judge FAIL: ${judgement.reasoning} (extracted ${judgement.extractedChars} chars)`,
  ).toBe(true)

  // ── Usage delta: must be EXACTLY 5 (FORM_FILL_PAGE_COST). Not ≥5 — if it's
  // more, we've double-charged somewhere and that is itself the bug. ─────
  const after = await (await request.get(`${BASE}/payments/subscription`, { headers: auth() })).json()
  const delta = after.pages_used - beforePages
  expect(
    delta,
    `Form-fill must charge EXACTLY 5 pages. beforePages=${beforePages} afterPages=${after.pages_used} delta=${delta}`,
  ).toBe(5)
})

// ── Schedules extraction happy path ──────────────────────────────────────────
test('Schedules: invoice PDF → queued job → completed → xlsx with invoice data + 1 page charged', async ({ request }) => {
  test.setTimeout(300_000)

  await resetUsage(request, 100)
  await new Promise(res => setTimeout(res, 1500))

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
  expect(typeof submit.job_id, 'no job_id returned').toBe('string')
  expect(submit.job_id.length, 'job_id suspiciously short').toBeGreaterThan(8)
  expect(submit.status).toBe('queued')

  const jobId = submit.job_id

  // Poll job status until a terminal state is reached (max 3 min).
  let final: any = null
  const deadline = Date.now() + 180_000
  while (Date.now() < deadline) {
    await new Promise(res => setTimeout(res, 2000))
    const jr = await request.get(`${BASE}/documents/job/${jobId}`, { headers: auth() })
    if (jr.status() !== 200) continue
    const j = await jr.json()
    const term = String(j.status || '').toLowerCase()
    if (['complete', 'completed', 'failed', 'error'].includes(term)) { final = j; break }
  }
  expect(final, 'job never reached terminal state within 180s').not.toBeNull()
  const finalStatus = String(final.status || '').toLowerCase()
  expect(['complete', 'completed'], `job ended in non-success state: ${finalStatus}`).toContain(finalStatus)

  // Download the result
  const dl = await request.get(`${BASE}/documents/download/${jobId}`, { headers: auth() })
  expect(dl.status()).toBe(200)
  const xlsx = await dl.body()

  // ── Content validation via LLM judge ───────────────────────────────────
  // Expectation: the xlsx contains at least one row with values that look
  // like the three requested fields (invoice number, total amount, vendor
  // name). The LLM sees the spreadsheet content and judges semantically.
  const judgement = await llmJudge(
    request,
    { name: 'extracted.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from(xlsx) },
    'This should be an extraction spreadsheet with columns or labels resembling '
    + '"invoice_number", "total_amount", and "vendor_name" (or close variants), and at least '
    + 'one populated data row where those three values are present and non-empty (a vendor '
    + 'name as a string, a total amount as a number or currency-formatted string, and an '
    + 'invoice/order identifier). An empty sheet, a headers-only sheet, or a sheet whose '
    + 'values are all null/placeholder text is a FAIL.',
  )
  expect(
    judgement.pass,
    `LLM judge FAIL: ${judgement.reasoning} (extracted ${judgement.extractedChars} chars)`,
  ).toBe(true)

  // ── Usage delta: must be EXACTLY 1 (invoice is a single-page PDF). ────
  const after = await (await request.get(`${BASE}/payments/subscription`, { headers: auth() })).json()
  const delta = after.pages_used - beforePages
  expect(
    delta,
    `Single-page invoice extraction must charge EXACTLY 1 page. beforePages=${beforePages} afterPages=${after.pages_used} delta=${delta}`,
  ).toBe(1)
})
