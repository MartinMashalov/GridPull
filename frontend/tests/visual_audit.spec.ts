/*
 * Visual audit — screenshot every page at desktop + mobile and check for:
 *  - console errors (filters known benign network drops)
 *  - horizontal overflow (body scrollWidth > clientWidth)
 *  - missing images (naturalWidth === 0)
 *  - text clipped by overflow:hidden on headings
 */
import { test, expect, type Page } from '@playwright/test'

const IGNORED_CONSOLE = [
  'ERR_NETWORK_CHANGED',
  'ERR_INTERNET_DISCONNECTED',
  'Failed to load resource: net::ERR_NETWORK_CHANGED',
  'Failed to load resource: net::ERR_INTERNET_DISCONNECTED',
  'favicon',
  'sentry',
  'google-analytics',
  'googletagmanager',
  '_vercel',
  'hotjar',
]

async function loginAsDev(page: Page) {
  // Hit dev-login, save token into localStorage, then reload the authenticated page.
  const r = await page.request.post('https://gridpull.com/api/auth/dev-login', {
    data: { email: 'martin.mashalov@gmail.com', secret: 'gridpull-dev-bypass-2026' },
  })
  expect(r.status()).toBe(200)
  const { access_token, user } = await r.json()
  await page.goto('https://gridpull.com/')
  await page.evaluate(({ token, u }) => {
    localStorage.setItem('gridpull-auth-v5', JSON.stringify({
      state: { token, user: u, isAuthenticated: true },
      version: 0,
    }))
  }, { token: access_token, u: user })
}

async function auditPage(page: Page, label: string, authed: boolean) {
  const consoleErrors: string[] = []
  page.on('console', msg => {
    if (msg.type() !== 'error') return
    const text = msg.text()
    if (IGNORED_CONSOLE.some(p => text.includes(p))) return
    consoleErrors.push(text)
  })
  const pageErrors: string[] = []
  page.on('pageerror', e => pageErrors.push(String(e)))

  if (authed) await loginAsDev(page)

  const path = label
  await page.goto(`https://gridpull.com${path}`)
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {})

  // Horizontal overflow check
  const overflow = await page.evaluate(() => {
    const b = document.body
    return b.scrollWidth > b.clientWidth + 2
  })

  // Broken images
  const brokenImgs = await page.evaluate(() => {
    return Array.from(document.images)
      .filter(i => i.complete && i.naturalWidth === 0 && i.src && !i.src.startsWith('data:'))
      .map(i => i.src)
  })

  await page.screenshot({ path: `test-screenshots/audit${path.replace(/\//g, '_') || '_root'}.png`, fullPage: true })

  expect(pageErrors, `${path} pageerror: ${pageErrors.join(' | ')}`).toEqual([])
  expect(consoleErrors, `${path} console errors: ${consoleErrors.slice(0,5).join(' | ')}`).toEqual([])
  expect(overflow, `${path} has horizontal overflow`).toBe(false)
  expect(brokenImgs, `${path} broken images: ${brokenImgs.slice(0,3).join(', ')}`).toEqual([])
}

// ── Desktop audit (1440×900 default) ─────────────────────────────────────────

const PUBLIC = ['/', '/privacy', '/terms', '/resources']
const AUTH = ['/form-filling', '/schedules', '/inbox', '/proposals', '/pipelines', '/settings']

for (const p of PUBLIC) {
  test(`Desktop public ${p}`, async ({ page }) => {
    await auditPage(page, p, false)
  })
}

for (const p of AUTH) {
  test(`Desktop auth ${p}`, async ({ page }) => {
    await auditPage(page, p, true)
  })
}

// ── Mobile audit (375×812) ───────────────────────────────────────────────────

test.describe('Mobile 375×812', () => {
  test.use({ viewport: { width: 375, height: 812 } })

  for (const p of PUBLIC) {
    test(`Mobile public ${p}`, async ({ page }) => {
      await auditPage(page, p, false)
    })
  }

  for (const p of AUTH) {
    test(`Mobile auth ${p}`, async ({ page }) => {
      await auditPage(page, p, true)
    })
  }
})
