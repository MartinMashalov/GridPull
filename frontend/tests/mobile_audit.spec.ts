import { test, expect, type Page, type ConsoleMessage } from '@playwright/test'
import path from 'path'
import fs from 'fs'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const SS = path.join(__dirname, '..', 'test-screenshots', 'mobile')
const L = '/auto-login?t=gridpull-dev-bypass-2026'

const IGNORED_CONSOLE = [
  /Download the React DevTools/i,
  /Stripe\.js was loaded/i,
  /\[HMR\]/i,
  /net::ERR_ABORTED.*analytics/i,
  /favicon\.ico/i,
  /googleusercontent\.com/i,
  /posthog/i,
  /ERR_NETWORK_CHANGED/i,
  /ERR_INTERNET_DISCONNECTED/i,
]

function trackConsole(page: Page) {
  const errors: { type: string; text: string }[] = []
  page.on('console', (msg: ConsoleMessage) => {
    if (msg.type() !== 'error') return
    const text = msg.text()
    if (IGNORED_CONSOLE.some((re) => re.test(text))) return
    errors.push({ type: msg.type(), text })
  })
  page.on('pageerror', (err) => errors.push({ type: 'pageerror', text: err.message }))
  return errors
}

async function login(page: Page) {
  await page.goto(L)
  await page.waitForURL((u) => !u.toString().includes('/auto-login'), { timeout: 20000 })
}

async function assertNoHorizontalOverflow(page: Page, label: string) {
  const { scrollW, clientW } = await page.evaluate(() => {
    const d = document.documentElement
    return { scrollW: d.scrollWidth, clientW: d.clientWidth }
  })
  expect(
    scrollW,
    `${label}: horizontal overflow (scrollW=${scrollW} clientW=${clientW})`,
  ).toBeLessThanOrEqual(clientW + 2)
}

async function assertRendered(page: Page, label: string) {
  const boundaryCount = await page.getByText(/Something went wrong/i).count()
  expect(boundaryCount, `${label}: ErrorBoundary visible`).toBe(0)
  const bodyLen = await page.evaluate(() => document.body.innerText.trim().length)
  expect(bodyLen, `${label}: empty body`).toBeGreaterThan(20)
}

// ─── Mobile phone: iPhone 12-ish ──────────────────────────────────────────
test.describe('mobile phone viewport (375x812)', () => {
  test.use({ viewport: { width: 375, height: 812 } })

  test.beforeAll(() => { fs.mkdirSync(SS, { recursive: true }) })

  const PUBLIC = [
    { path: '/', label: 'landing' },
    { path: '/privacy', label: 'privacy' },
    { path: '/terms', label: 'terms' },
  ]
  for (const r of PUBLIC) {
    test(`public ${r.path} on phone`, async ({ page }) => {
      const errs = trackConsole(page)
      await page.goto(r.path, { waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(800)
      await assertRendered(page, `phone${r.path}`)
      await assertNoHorizontalOverflow(page, `phone${r.path}`)
      await page.screenshot({ path: path.join(SS, `phone_public_${r.label}.png`), fullPage: true })
      expect(errs, `Console errors: ${JSON.stringify(errs.slice(0, 5))}`).toEqual([])
    })
  }

  const PROTECTED = [
    { path: '/form-filling', label: 'form_filling' },
    { path: '/schedules', label: 'schedules' },
    { path: '/inbox', label: 'inbox' },
    { path: '/proposals', label: 'proposals' },
    { path: '/pipelines', label: 'pipelines' },
    { path: '/settings', label: 'settings' },
  ]
  for (const r of PROTECTED) {
    test(`protected ${r.path} on phone`, async ({ page }) => {
      const errs = trackConsole(page)
      await login(page)
      await page.goto(r.path, { waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(1500)
      await assertRendered(page, `phone${r.path}`)
      await assertNoHorizontalOverflow(page, `phone${r.path}`)
      await page.screenshot({ path: path.join(SS, `phone_protected_${r.label}.png`), fullPage: true })
      expect(errs, `Console errors on ${r.path}: ${JSON.stringify(errs.slice(0, 5))}`).toEqual([])
    })
  }

  // The mobile hamburger must actually open a drawer with nav links
  test('phone hamburger opens nav drawer', async ({ page }) => {
    await login(page)
    await page.goto('/form-filling')
    await page.waitForTimeout(1200)
    // There should be a hamburger button; click it
    const hamburger = page.locator('button').filter({ has: page.locator('svg') }).first()
    await expect(hamburger).toBeVisible()
    await hamburger.click()
    // The drawer should surface nav labels
    await expect(page.getByText(/Schedules/).first()).toBeVisible({ timeout: 5000 })
    await page.screenshot({ path: path.join(SS, 'phone_drawer_open.png'), fullPage: true })
  })
})

// ─── Tablet viewport: iPad portrait ───────────────────────────────────────
test.describe('tablet viewport (768x1024)', () => {
  test.use({ viewport: { width: 768, height: 1024 } })

  const PROTECTED = [
    { path: '/form-filling', label: 'form_filling' },
    { path: '/schedules', label: 'schedules' },
    { path: '/settings', label: 'settings' },
  ]
  for (const r of PROTECTED) {
    test(`protected ${r.path} on tablet`, async ({ page }) => {
      const errs = trackConsole(page)
      await login(page)
      await page.goto(r.path, { waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(1500)
      await assertRendered(page, `tablet${r.path}`)
      await assertNoHorizontalOverflow(page, `tablet${r.path}`)
      await page.screenshot({ path: path.join(SS, `tablet_protected_${r.label}.png`), fullPage: true })
      expect(errs, `Console errors on ${r.path}: ${JSON.stringify(errs.slice(0, 5))}`).toEqual([])
    })
  }
})
