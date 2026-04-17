import { test, expect } from '@playwright/test'
import path from 'path'
import { fileURLToPath } from 'url'
const __dirname = path.dirname(fileURLToPath(import.meta.url))
const SS = path.join(__dirname, '..', 'test-screenshots', 'interactive')
const L = '/auto-login?t=gridpull-dev-bypass-2026'

test.describe('Landing Page Interactions', () => {
  test('hero CTA opens sign-in dialog', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.screenshot({ path: path.join(SS, '01_landing_hero.png') })
    await page.getByText('Start free', { exact: false }).first().click()
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(SS, '02_signin_dialog.png') })
    await page.keyboard.press('Escape')
  })

  test('navbar scrolls to sections', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.locator('header').getByText('Tools').click()
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(SS, '03_tools_scrolled.png') })
    await page.locator('header').getByText('Pricing').click()
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(SS, '05_pricing_scrolled.png') })
  })

  test('FAQ accordion', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.getByText('How much does it cost?').scrollIntoViewIfNeeded()
    await page.getByText('How much does it cost?').click()
    await page.waitForTimeout(300)
    await page.screenshot({ path: path.join(SS, '06_faq_expanded.png') })
    await page.getByText('Are my files secure?').click()
    await page.waitForTimeout(300)
    await page.screenshot({ path: path.join(SS, '07_faq_security.png') })
  })

  test('mobile layout', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.screenshot({ path: path.join(SS, '08_mobile_hero.png') })
  })
})

test.describe('Sidebar Navigation', () => {
  test('all nav items', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    const pages = ['form-filling', 'schedules', 'inbox', 'proposals', 'pipelines', 'settings']
    for (const p of pages) {
      await page.goto('/' + p)
      await page.waitForLoadState('networkidle')
      await page.waitForTimeout(500)
      await page.screenshot({ path: path.join(SS, '20_nav_' + p + '.png') })
    }
  })

  test('sidebar collapse', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.goto('/form-filling')
    await page.waitForLoadState('networkidle')
    const collapse = page.locator('aside button[title="Collapse sidebar"]')
    if (await collapse.isVisible()) {
      await collapse.click()
      await page.waitForTimeout(400)
      await page.screenshot({ path: path.join(SS, '21_sidebar_collapsed.png') })
    }
  })

  test('user menu', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.goto('/form-filling')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(500)
    const userArea = page.locator('aside .text-xs.font-medium.truncate').locator('..')
    if (await userArea.isVisible()) {
      await userArea.click()
      await page.waitForTimeout(300)
      await page.screenshot({ path: path.join(SS, '23_user_menu.png') })
    }
  })
})

test.describe('Form Filling', () => {
  test('empty state', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.goto('/form-filling')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(SS, '30_formfill_empty.png') })
  })
})

test.describe('Schedules', () => {
  test('empty state', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.goto('/schedules')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(SS, '40_schedules.png') })
  })
})

test.describe('Document Inbox', () => {
  test('inbox with docs', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.goto('/inbox')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.screenshot({ path: path.join(SS, '50_inbox.png') })
  })

  test('select doc shows actions', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.goto('/inbox')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    const checkbox = page.locator('[role="checkbox"]').first()
    if (await checkbox.isVisible()) {
      await checkbox.click()
      await page.waitForTimeout(300)
      await page.screenshot({ path: path.join(SS, '52_inbox_selected.png') })
    }
  })
})

test.describe('Proposals - Upgrade Gate', () => {
  test('free user sees upgrade prompt', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.evaluate(() => {
      const raw = localStorage.getItem('gridpull-auth-v5')
      if (raw) {
        const data = JSON.parse(raw)
        if (data.state && data.state.user) data.state.user.subscription_tier = 'free'
        localStorage.setItem('gridpull-auth-v5', JSON.stringify(data))
      }
    })
    await page.goto('/proposals')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)
    await page.screenshot({ path: path.join(SS, '60_proposals_free_gate.png'), fullPage: true })
    await expect(page.getByText('Proposals require a Pro plan')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Upgrade to Pro' })).toBeVisible()
  })

  test('pro user sees full form', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.goto('/proposals')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(SS, '62_proposals_pro.png'), fullPage: true })
    await expect(page.getByRole('heading', { name: 'Proposals' })).toBeVisible()
  })
})

test.describe('Pipelines - Upgrade Gate', () => {
  test('free user sees upgrade prompt on pipelines', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.evaluate(() => {
      const raw = localStorage.getItem('gridpull-auth-v5')
      if (raw) {
        const data = JSON.parse(raw)
        if (data.state && data.state.user) data.state.user.subscription_tier = 'free'
        localStorage.setItem('gridpull-auth-v5', JSON.stringify(data))
      }
    })
    await page.goto('/pipelines')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)
    await page.screenshot({ path: path.join(SS, '72_pipelines_free_gate.png'), fullPage: true })
    await expect(page.getByText('Pipelines require a Pro plan')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Upgrade to Pro' })).toBeVisible()
  })
})

test.describe('Settings', () => {
  test('all tabs', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(SS, '80_settings_sub.png') })
    await page.getByText('Usage').click()
    await page.waitForTimeout(1000)
    await page.screenshot({ path: path.join(SS, '81_settings_usage.png') })
    await page.getByText('Profile').click()
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(SS, '82_settings_profile.png') })
  })

  test('no presets tab', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(500)
    await expect(page.locator('button:has-text("Presets")')).not.toBeVisible()
    await expect(page.locator('button:has-text("Defaults")')).not.toBeVisible()
  })
})
