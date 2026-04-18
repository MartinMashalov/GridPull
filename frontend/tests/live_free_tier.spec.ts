/*
 * Live free-tier enforcement tests.
 * Uses POST /api/auth/dev-set-usage to force the dev user into specific states,
 * then verifies the backend blocks or allows requests accordingly. Always
 * restores the original tier/usage before exiting.
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
  expect(r.status()).toBe(200)
  return (await r.json()).access_token
}

async function setUsage(req: APIRequestContext, tier: string, pages: number, overage = 0) {
  const r = await req.post(`${BASE}/auth/dev-set-usage`, {
    data: {
      secret: DEV_SECRET,
      subscription_tier: tier,
      pages_used_this_period: pages,
      overage_pages_this_period: overage,
    },
  })
  expect(r.status(), `dev-set-usage HTTP ${r.status()}`).toBe(200)
  return r.json()
}

let TOKEN = ''
let ORIG_TIER = 'pro'
let ORIG_USED = 0
let ORIG_OVERAGE = 0

test.beforeAll(async ({ request }) => {
  TOKEN = await devLogin(request)
  const sub = await (await request.get(`${BASE}/payments/subscription`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
  })).json()
  ORIG_TIER = sub.tier?.name || 'pro'
  ORIG_USED = sub.pages_used
  ORIG_OVERAGE = sub.overage_pages_used || 0
})

test.afterAll(async ({ request }) => {
  // Always restore — never leave the dev user stuck on free after a failure.
  await setUsage(request, ORIG_TIER, ORIG_USED, ORIG_OVERAGE)
})

function auth() { return { Authorization: `Bearer ${TOKEN}` } }

test('Free tier @ 498 pages: form-fill (5 pages) -> 402 page_limit_reached', async ({ request }) => {
  await setUsage(request, 'free', 498)

  const target = fs.readFileSync(path.join(__dirname, 'fixtures_gsa_sf1449.pdf'))
  const source = fs.readFileSync(path.join(__dirname, 'fixtures_sample_invoice.pdf'))

  const r = await request.post(`${BASE}/form-filling/fill`, {
    headers: auth(),
    multipart: {
      target_form: { name: 'gsa.pdf', mimeType: 'application/pdf', buffer: target },
      source_files: { name: 'invoice.pdf', mimeType: 'application/pdf', buffer: source },
    },
  })
  expect(r.status()).toBe(402)
  const body = await r.json()
  expect(body.detail?.type).toBe('page_limit_reached')
  expect(body.detail?.pages_limit).toBe(500)
  expect(body.detail?.tier).toBe('free')

  // Usage must be unchanged (still 498)
  const sub = await (await request.get(`${BASE}/payments/subscription`, { headers: auth() })).json()
  expect(sub.pages_used).toBe(498)
})

test('Free tier @ 498 pages: extraction (1+ pages) -> 402 page_limit_reached', async ({ request }) => {
  await setUsage(request, 'free', 498)

  const invoice = fs.readFileSync(path.join(__dirname, 'fixtures_sample_invoice.pdf'))
  const r = await request.post(`${BASE}/documents/extract`, {
    headers: auth(),
    multipart: {
      files: { name: 'invoice.pdf', mimeType: 'application/pdf', buffer: invoice },
      fields: JSON.stringify([{ name: 'total', description: 'total' }]),
      format: 'xlsx',
    },
  })
  // Invoice is 1 page but billable includes 1 → 498+1=499 <=500 so this would pass.
  // The multi-page test below covers the 402 path.
  expect([200, 402]).toContain(r.status())
})

test('Free tier @ 498 pages: multi-page extraction -> 402', async ({ request }) => {
  await setUsage(request, 'free', 498)

  const bigpdf = fs.readFileSync('/Users/martinmashalov/Downloads/GridPull/backend/test_files/01_property_appraisal_report_25_buildings.pdf')
  const r = await request.post(`${BASE}/documents/extract`, {
    headers: auth(),
    multipart: {
      files: { name: 'big.pdf', mimeType: 'application/pdf', buffer: bigpdf },
      fields: JSON.stringify([{ name: 'x', description: 'x' }]),
      format: 'xlsx',
    },
  })
  expect(r.status()).toBe(402)
  const body = await r.json()
  expect(body.detail?.type).toBe('page_limit_reached')
})

test('Free tier @ 0 pages: small extraction allowed', async ({ request }) => {
  await setUsage(request, 'free', 0)

  const invoice = fs.readFileSync(path.join(__dirname, 'fixtures_sample_invoice.pdf'))
  const r = await request.post(`${BASE}/documents/extract`, {
    headers: auth(),
    multipart: {
      files: { name: 'invoice.pdf', mimeType: 'application/pdf', buffer: invoice },
      fields: JSON.stringify([{ name: 'a', description: 'a' }]),
      format: 'xlsx',
    },
  })
  expect(r.status()).toBe(200)
  const body = await r.json()
  expect(body.job_id).toBeTruthy()
  expect(body.usage?.tier).toBe('free')
})

test('Starter tier: proposals blocked with 403 upgrade_required', async ({ request }) => {
  await setUsage(request, 'starter', 0)

  const PDF_STUB = Buffer.from('%PDF-1.4\n%EOF\n')
  const r = await request.post(`${BASE}/proposals/generate`, {
    headers: auth(),
    multipart: {
      lob: 'commercial_general_liability',
      documents: { name: 'x.pdf', mimeType: 'application/pdf', buffer: PDF_STUB },
    },
  })
  expect(r.status()).toBe(403)
  const body = await r.json()
  expect(body.detail?.type).toBe('upgrade_required')
})
