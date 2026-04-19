/*
 * Proposals happy-path against live gridpull.com.
 * Generates a proposal from a sample quote PDF and LLM-judges the output.
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

async function llmJudge(
  req: APIRequestContext,
  artifact: { name: string; mimeType: string; buffer: Buffer },
  expectation: string,
) {
  const r = await req.post(`${BASE}/auth/dev-llm-judge`, {
    multipart: { secret: DEV_SECRET, expectation, file: artifact },
    timeout: 60_000,
  })
  const status = r.status()
  const text = await r.text()
  if (status !== 200) throw new Error(`llm-judge HTTP ${status}: ${text.slice(0, 400)}`)
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

test('Proposals: quote PDF → branded PDF proposal + exactly 5 pages charged', async ({ request }) => {
  test.setTimeout(600_000)

  await resetUsage(request, 100)
  await new Promise(res => setTimeout(res, 1500))

  const before = await (await request.get(`${BASE}/payments/subscription`, { headers: auth() })).json()
  const beforePages = before.pages_used

  // Reuse the sample invoice fixture as a pretend carrier quote — good enough
  // for Papyra to produce a proposal PDF and for the judge to evaluate.
  const quote = fs.readFileSync(path.join(__dirname, 'fixtures_sample_invoice.pdf'))

  const r = await request.post(`${BASE}/proposals/generate`, {
    headers: auth(),
    multipart: {
      lob: 'commercial_property',
      user_context: 'Small business client',
      agency_info: 'GridPull Insurance Agency\ncontact@gridpull.com',
      brand_primary: '#1A3560',
      brand_accent: '#C9901E',
      documents: { name: 'quote.pdf', mimeType: 'application/pdf', buffer: quote },
    },
    timeout: 600_000,
  })
  const status = r.status()
  const body = await r.text()
  expect(status, `generate status=${status} body=${body.slice(0, 400)}`).toBe(200)

  const payload = JSON.parse(body)
  const b64 = payload.pdf_base64 || payload.pdf || payload.file_base64 || payload.document?.pdf_base64
  expect(typeof b64, `no pdf_base64 in response keys: ${Object.keys(payload).join(',')}`).toBe('string')
  expect((b64 as string).length).toBeGreaterThan(1000)
  const pdfBuffer = Buffer.from(b64 as string, 'base64')
  expect(pdfBuffer.slice(0, 5).toString('utf8')).toBe('%PDF-')

  // Content check via LLM judge
  const judgement = await llmJudge(
    request,
    { name: 'proposal.pdf', mimeType: 'application/pdf', buffer: pdfBuffer },
    'This should be a polished, client-ready insurance proposal PDF in the '
    + 'style of a broker presenting quotes to an insured. It should reference '
    + 'the client or LOB (commercial property), include recognizable insurance '
    + 'language (premium, coverage, limits, deductible, carrier), and contain '
    + 'structured sections rather than being a raw quote passthrough. A blank '
    + 'PDF, a generic "Hello World" PDF, or a PDF that is just the original '
    + 'uploaded quote unchanged is a FAIL.',
  )
  expect(
    judgement.pass,
    `LLM judge FAIL: ${judgement.reasoning} (extracted ${judgement.extractedChars} chars)`,
  ).toBe(true)

  // Usage delta must be EXACTLY 5 (PROPOSAL_PAGE_COST)
  const after = await (await request.get(`${BASE}/payments/subscription`, { headers: auth() })).json()
  const delta = after.pages_used - beforePages
  expect(
    delta,
    `Proposal must charge EXACTLY 5 pages. beforePages=${beforePages} afterPages=${after.pages_used} delta=${delta}`,
  ).toBe(5)
})
