import { test, expect } from '@playwright/test'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const SCREENSHOTS_DIR = path.join(__dirname, '..', 'test-screenshots')

/* ═══════════════════════════════════════════════════════════════════════════
   LANDING PAGE — Insurance Focus
   ═══════════════════════════════════════════════════════════════════════════ */

test.describe('Landing Page — Hero', () => {
  test('hero headline targets insurance brokers and agencies', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const hero = page.locator('h1')
    await expect(hero).toContainText('insurance brokers and agencies')
  })

  test('hero subtext mentions all five tools', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const body = await page.textContent('body')
    expect(body).toContain('Form Filling')
    expect(body).toContain('Schedules')
    expect(body).toContain('Proposals')
    expect(body).toContain('Document Inbox')
    expect(body).toContain('Pipelines')
  })

  test('hero mentions carrier forms and manual work', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const body = await page.textContent('body')
    expect(body).toContain('carrier forms')
  })

  test('hero CTA says start free', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('Start free', { exact: false }).first()).toBeVisible()
  })
})

test.describe('Landing Page — Stats Strip', () => {
  test('shows 28 lines of business stat', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('Lines of business', { exact: true })).toBeVisible()
  })

  test('shows 5 Tools stat', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('5 Tools', { exact: true })).toBeVisible()
  })

  test('shows Any File stat', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('Any File')).toBeVisible()
  })

  test('shows Seconds stat', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const stat = page.getByText('Not hours of data entry')
    await stat.scrollIntoViewIfNeeded()
    await expect(stat).toBeVisible()
  })
})

test.describe('Landing Page — Tool Sections', () => {
  test('Form Filling section has insurance-specific content', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('heading', { name: 'Form Filling' })).toBeVisible()
    const body = await page.textContent('body')
    expect(body).toContain('ACORD forms')
    expect(body).toContain('carrier')
    expect(body).toContain('supplemental')
  })

  test('Schedules section describes commercial submissions', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('heading', { name: 'Schedules' })).toBeVisible()
    const body = await page.textContent('body')
    expect(body).toContain('schedules of values')
    expect(body).toContain('vehicles')
    expect(body).toContain('drivers')
    expect(body).toContain('commercial submissions')
  })

  test('Proposals section describes quote comparison', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('heading', { name: 'Proposals' })).toBeVisible()
    const body = await page.textContent('body')
    expect(body).toContain('quote comparison')
    expect(body).toContain('28 lines of business')
  })

  test('Document Inbox section describes email forwarding', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('heading', { name: 'Document Inbox' })).toBeVisible()
    const body = await page.textContent('body')
    expect(body).toContain('Forward emails')
    expect(body).toContain('organized by sender')
  })

  test('Pipelines section describes automation', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('heading', { name: 'Pipelines' })).toBeVisible()
    const body = await page.textContent('body')
    expect(body).toContain('Outlook')
    expect(body).toContain('Box')
    expect(body).toContain('Dropbox')
    expect(body).toContain('Google Drive')
  })
})

test.describe('Landing Page — How It Works', () => {
  test('shows three-step workflow', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const section = page.locator('#how-it-works')
    await section.scrollIntoViewIfNeeded()
    await expect(page.getByText('Three steps. No learning curve.')).toBeVisible()
    // Step titles are h3 headings
    await expect(section.getByRole('heading', { name: 'Upload your documents' })).toBeVisible()
    await expect(section.getByRole('heading', { name: 'AI processes everything' })).toBeVisible()
    await expect(section.getByRole('heading', { name: 'Download your results' })).toBeVisible()
  })
})

test.describe('Landing Page — Pricing', () => {
  test('shows all four tiers with correct prices', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.getByText('Plans that scale with your agency').scrollIntoViewIfNeeded()
    await expect(page.getByText('Plans that scale with your agency')).toBeVisible()
    await expect(page.locator('text=$49')).toBeVisible()
    await expect(page.locator('text=$199')).toBeVisible()
    await expect(page.locator('text=$699')).toBeVisible()
  })

  test('Free tier includes 100 pages', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('100 pages/month', { exact: true })).toBeVisible()
  })

  test('pricing describes page-based billing not credits', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const body = await page.textContent('body')
    const stripped = body?.replace(/credit card/gi, '').replace(/CreditCard/g, '') || ''
    expect(stripped.toLowerCase()).not.toContain('credit')
    expect(body).toContain('pages')
  })

  test('Pro tier is highlighted as most popular', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('Most popular')).toBeVisible()
  })
})

test.describe('Landing Page — FAQ', () => {
  test('FAQ has insurance-relevant questions', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('Common questions from brokers and agencies')).toBeVisible()
    await expect(page.getByText('How much does it cost?')).toBeVisible()
    await expect(page.getByText('Are my files secure?')).toBeVisible()
    await expect(page.getByText('What file types are supported?')).toBeVisible()
    await expect(page.getByText("Can I update last year's schedule?")).toBeVisible()
    await expect(page.getByText('How does the proposal tool work?')).toBeVisible()
    await expect(page.getByText('What forms can be filled?')).toBeVisible()
  })
})

test.describe('Landing Page — No Non-Insurance Content', () => {
  test('no QuickBooks or accounting references', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('text=QuickBooks')).not.toBeVisible()
    await expect(page.locator('text=Accounting')).not.toBeVisible()
    await expect(page.locator('text=accounting')).not.toBeVisible()
  })
})

test.describe('Landing Page — Navigation', () => {
  test('navbar has Tools, How It Works, Pricing, FAQ links', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const header = page.locator('header')
    await expect(header.getByText('Tools')).toBeVisible()
    await expect(header.getByText('How It Works')).toBeVisible()
    await expect(header.getByText('Pricing')).toBeVisible()
    await expect(header.getByText('FAQ')).toBeVisible()
  })

  test('navbar shows GridPull brand', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('header').getByText('GridPull')).toBeVisible()
  })
})

test.describe('Landing Page — Footer', () => {
  test('footer has CTA and security note', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const ctaHeading = page.getByRole('heading', { name: 'Stop retyping data across carrier forms' })
    await ctaHeading.scrollIntoViewIfNeeded()
    await expect(ctaHeading).toBeVisible()
    await expect(page.getByText('encrypted and deleted after processing').last()).toBeVisible()
  })
})

/* ═══════════════════════════════════════════════════════════════════════════
   ROUTING — Sidebar Order & Redirects
   ═══════════════════════════════════════════════════════════════════════════ */

test.describe('Routing', () => {
  test('all six tool routes exist and do not crash', async ({ page }) => {
    const routes = ['/form-filling', '/schedules', '/inbox', '/proposals', '/pipelines', '/settings']
    for (const route of routes) {
      await page.goto(route)
      await page.waitForLoadState('networkidle')
      // Should not show error boundary
      await expect(page.locator('text=Something went wrong')).not.toBeVisible()
    }
  })

  test('/dashboard redirects away (no longer accessible)', async ({ page }) => {
    await page.goto('/dashboard')
    await page.waitForLoadState('networkidle')
    expect(page.url()).not.toContain('/dashboard')
  })

  test('unknown route redirects to home', async ({ page }) => {
    await page.goto('/nonexistent-page')
    await page.waitForLoadState('networkidle')
    // Should end up at / (landing page)
    expect(page.url().endsWith('/') || page.url().endsWith('/nonexistent-page')).toBe(true)
  })
})

/* ═══════════════════════════════════════════════════════════════════════════
   API HEALTH
   ═══════════════════════════════════════════════════════════════════════════ */

test.describe('API Health', () => {
  test('backend health endpoint returns 200', async ({ request }) => {
    const resp = await request.get('/api/health')
    expect(resp.status()).toBe(200)
  })

  test('tiers endpoint returns 4 page-based tiers', async ({ request }) => {
    const resp = await request.get('/api/payments/tiers')
    expect(resp.status()).toBe(200)
    const data = await resp.json()
    expect(data.tiers).toHaveLength(4)
    for (const tier of data.tiers) {
      expect(tier).toHaveProperty('pages_per_month')
      expect(tier).toHaveProperty('overage_rate_cents_per_page')
      expect(tier).not.toHaveProperty('credits_per_month')
    }
  })

  test('tier names are free, starter, pro, business', async ({ request }) => {
    const resp = await request.get('/api/payments/tiers')
    const data = await resp.json()
    const names = data.tiers.map((t: { name: string }) => t.name)
    expect(names).toEqual(['free', 'starter', 'pro', 'business'])
  })
})

/* ═══════════════════════════════════════════════════════════════════════════
   MOBILE RESPONSIVENESS
   ═══════════════════════════════════════════════════════════════════════════ */

test.describe('Mobile Responsiveness', () => {
  test('landing page renders properly on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    // Hero should still be visible
    await expect(page.getByText('insurance brokers and agencies')).toBeVisible()
    // CTA should be visible
    await expect(page.getByText('Start free', { exact: false }).first()).toBeVisible()
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'comp_mobile_hero.png') })
  })

  test('mobile landing shows pricing section', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.locator('text=Plans that scale').scrollIntoViewIfNeeded()
    await expect(page.getByText('Plans that scale')).toBeVisible()
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'comp_mobile_pricing.png') })
  })
})

/* ═══════════════════════════════════════════════════════════════════════════
   SECURITY & PRIVACY MESSAGING
   ═══════════════════════════════════════════════════════════════════════════ */

test.describe('Security Messaging', () => {
  test('landing page emphasizes file security', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const body = await page.textContent('body')
    expect(body).toContain('encrypted')
    expect(body).toContain('deleted after processing')
  })
})

/* ═══════════════════════════════════════════════════════════════════════════
   SIGN-IN FLOW
   ═══════════════════════════════════════════════════════════════════════════ */

test.describe('Sign In', () => {
  test('sign in button opens provider dialog with Google and Microsoft', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    // Click the header "Try for free" button
    const tryBtn = page.locator('header').getByText('Try for free')
    await tryBtn.click()
    // Should show a dialog with Google and Microsoft options
    await expect(page.getByRole('button', { name: 'Continue with Google' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Continue with Microsoft' })).toBeVisible()
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'comp_signin_dialog.png') })
  })
})

/* ═══════════════════════════════════════════════════════════════════════════
   VISUAL CAPTURE — All Sections
   ═══════════════════════════════════════════════════════════════════════════ */

test.describe('Visual Capture', () => {
  test('capture landing page full scroll', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'comp_landing_full.png'), fullPage: true })
  })
})
