import { test, expect, type Page, type ConsoleMessage } from '@playwright/test'
import path from 'path'
import fs from 'fs'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const SS = path.join(__dirname, '..', 'test-screenshots', 'audit')
const L = '/auto-login?t=gridpull-dev-bypass-2026'

async function login(page: Page) {
  await page.goto(L)
  await page.waitForURL((u) => !u.toString().includes('/auto-login'), { timeout: 20000 })
  const token = await page.evaluate(() => {
    const raw = localStorage.getItem('gridpull-auth-v5')
    if (!raw) return null
    try { return JSON.parse(raw)?.state?.token ?? null } catch { return null }
  })
  expect(token, 'Auto-login did not persist an access token').toBeTruthy()
}

// Real errors we care about; filter out third-party / benign chatter so signal is high.
const IGNORED_CONSOLE = [
  /Download the React DevTools/i,
  /Stripe\.js was loaded/i,
  /\[HMR\]/i,
  /net::ERR_ABORTED.*analytics/i,
  /favicon\.ico/i,
  /googleusercontent\.com/i,
  /posthog/i,
]
function trackConsole(page: Page) {
  const errors: { type: string; text: string; location?: string }[] = []
  page.on('console', (msg: ConsoleMessage) => {
    if (msg.type() !== 'error') return
    const text = msg.text()
    if (IGNORED_CONSOLE.some((re) => re.test(text))) return
    const loc = msg.location?.() ?? {}
    errors.push({ type: msg.type(), text, location: `${loc.url ?? ''}:${loc.lineNumber ?? 0}` })
  })
  page.on('pageerror', (err) => errors.push({ type: 'pageerror', text: err.message }))
  page.on('response', (resp) => {
    if (resp.status() >= 500 && resp.url().startsWith('https://gridpull.com/api/')) {
      errors.push({ type: '5xx', text: `${resp.status()} ${resp.url()}` })
    }
  })
  return errors
}

// Screenshot a page + detect obviously-broken layout conditions.
async function capture(page: Page, label: string) {
  fs.mkdirSync(SS, { recursive: true })
  await page.screenshot({ path: path.join(SS, `${label}.png`), fullPage: true })
}

// "Is the page actually rendering content?" — horizontal scroll, empty body, or an ErrorBoundary message all count as broken.
async function assertRenderedHealthy(page: Page, label: string) {
  const boundaryText = await page.getByText(/Something went wrong/i).count()
  expect(boundaryText, `${label}: ErrorBoundary fallback is visible`).toBe(0)

  const bodyText = await page.evaluate(() => document.body.innerText.trim().length)
  expect(bodyText, `${label}: page body is empty`).toBeGreaterThan(20)

  // Horizontal overflow == layout bug at this viewport
  const overflow = await page.evaluate(() => {
    const d = document.documentElement
    return { scrollW: d.scrollWidth, clientW: d.clientWidth }
  })
  expect(
    overflow.scrollW,
    `${label}: horizontal overflow (scrollW=${overflow.scrollW} clientW=${overflow.clientW})`,
  ).toBeLessThanOrEqual(overflow.clientW + 2)
}

// ─── Public routes ──────────────────────────────────────────────────────────
const PUBLIC_ROUTES: { path: string; label: string; expect?: RegExp }[] = [
  { path: '/', label: 'landing' },
  { path: '/privacy', label: 'privacy' },
  { path: '/terms', label: 'terms' },
  { path: '/resources', label: 'resources_hub' },
]

for (const r of PUBLIC_ROUTES) {
  test(`public route renders: ${r.path}`, async ({ page }) => {
    const errs = trackConsole(page)
    const resp = await page.goto(r.path, { waitUntil: 'domcontentloaded' })
    expect(resp?.status(), `${r.path} HTTP status`).toBeLessThan(400)
    await page.waitForLoadState('domcontentloaded')
    // Give React a tick to mount
    await page.waitForTimeout(800)
    await assertRenderedHealthy(page, r.path)
    await capture(page, `public_${r.label}`)
    expect(errs, `Console errors on ${r.path}: ${JSON.stringify(errs.slice(0, 5))}`).toEqual([])
  })
}

// ─── Protected routes ───────────────────────────────────────────────────────
const PROTECTED_ROUTES: { path: string; label: string; anchor?: RegExp; afterLoad?: (page: Page) => Promise<void> }[] = [
  { path: '/form-filling', label: 'form_filling', anchor: /Fill Applications|Upload|Target Form|Source/i },
  { path: '/schedules',    label: 'schedules',    anchor: /Schedules|Extract|Upload/i },
  { path: '/inbox',        label: 'inbox',        anchor: /Inbox|ingest|email/i },
  { path: '/proposals',    label: 'proposals',    anchor: /Propos|Agency|Line of Business/i },
  { path: '/pipelines',    label: 'pipelines',    anchor: /Pipeline|Connect|Google|Dropbox/i },
  { path: '/settings',     label: 'settings',     anchor: /Settings|Plan|Subscription|Card/i },
]

for (const r of PROTECTED_ROUTES) {
  test(`protected route renders: ${r.path}`, async ({ page }) => {
    const errs = trackConsole(page)
    await login(page)
    const resp = await page.goto(r.path, { waitUntil: 'domcontentloaded' })
    expect(resp?.status(), `${r.path} HTTP status`).toBeLessThan(400)
    // Wait for either the anchor to appear or a reasonable settle time
    if (r.anchor) {
      await expect(page.getByText(r.anchor).first()).toBeVisible({ timeout: 15000 })
    } else {
      await page.waitForTimeout(1200)
    }
    await assertRenderedHealthy(page, r.path)
    await capture(page, `protected_${r.label}`)
    expect(errs, `Console errors on ${r.path}: ${JSON.stringify(errs.slice(0, 5))}`).toEqual([])
  })
}

// ─── Navigation regression: every sidebar link should reach a real page ────
test('sidebar navigation: every link routes to a non-broken page', async ({ page }) => {
  const errs = trackConsole(page)
  await login(page)
  await page.goto('/form-filling')

  const targets = [
    { name: /Fill Applications/i, url: /\/form-filling/ },
    { name: /Schedules/i,         url: /\/schedules/ },
    { name: /Document Inbox/i,    url: /\/inbox/ },
    { name: /Proposals/i,         url: /\/proposals/ },
    { name: /Pipelines/i,         url: /\/pipelines/ },
    { name: /Settings/i,          url: /\/settings/ },
  ]

  for (const t of targets) {
    const btn = page.getByRole('button', { name: t.name }).first()
    await btn.click()
    await page.waitForURL(t.url, { timeout: 10000 })
    await assertRenderedHealthy(page, `nav→${t.url}`)
  }
  expect(errs, `Console errors during nav sweep: ${JSON.stringify(errs.slice(0, 5))}`).toEqual([])
})

// ─── Images: none should be broken (naturalWidth>0 for every <img> that finished loading) ──
test('no broken <img> elements across primary pages', async ({ page }) => {
  await login(page)
  const pages = ['/form-filling', '/schedules', '/inbox', '/proposals', '/pipelines', '/settings']
  const broken: { page: string; src: string }[] = []
  for (const p of pages) {
    await page.goto(p)
    await page.waitForTimeout(1500)
    const bad = await page.$$eval('img', (imgs) =>
      imgs
        .filter((i) => (i as HTMLImageElement).complete)
        .filter((i) => (i as HTMLImageElement).naturalWidth === 0)
        .map((i) => (i as HTMLImageElement).src),
    )
    bad.forEach((src) => broken.push({ page: p, src }))
  }
  expect(broken, `Broken images: ${JSON.stringify(broken.slice(0, 10))}`).toEqual([])
})
