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
    await page.locator('header').getByText('How It Works').click()
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(SS, '04_howitworks_scrolled.png') })
    await page.locator('header').getByText('Pricing').click()
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(SS, '05_pricing_scrolled.png') })
  })

  test('FAQ accordion expand', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.getByText('How much does it cost?').scrollIntoViewIfNeeded()
    await page.getByText('How much does it cost?').click()
    await page.waitForTimeout(300)
    await page.screenshot({ path: path.join(SS, '06_faq_expanded.png') })
    await page.getByText('Are my files secure?').click()
    await page.waitForTimeout(300)
    await page.screenshot({ path: path.join(SS, '07_faq_security_expanded.png') })
  })

  test('mobile landing layout', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.screenshot({ path: path.join(SS, '08_mobile_hero.png') })
    await page.evaluate(() => window.scrollTo(0, 2000))
    await page.waitForTimeout(300)
    await page.screenshot({ path: path.join(SS, '09_mobile_tools.png') })
  })
})

test.describe('Sidebar Navigation', () => {
  test('all nav items and active states', async ({ page }) => {
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

  test('sidebar collapse and expand', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.goto('/form-filling')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(500)
    const collapse = page.locator('aside button[title="Collapse sidebar"]')
    if (await collapse.isVisible()) {
      await collapse.click()
      await page.waitForTimeout(400)
      await page.screenshot({ path: path.join(SS, '21_sidebar_collapsed.png') })
      await page.locator('aside').click()
      await page.waitForTimeout(400)
      await page.screenshot({ path: path.join(SS, '22_sidebar_expanded.png') })
    }
  })

  test('user menu at sidebar bottom', async ({ page }) => {
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
      await page.screenshot({ path: path.join(SS, '23_user_menu_open.png') })
    }
  })
})

test.describe('Form Filling Interactions', () => {
  test('empty state with how-it-works', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.goto('/form-filling')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(SS, '30_formfill_empty.png') })
  })

  test('dropzone hover states', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.goto('/form-filling')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(500)
    const target = page.locator('text=Drop a PDF form here').locator('..')
    await target.hover()
    await page.waitForTimeout(200)
    await page.screenshot({ path: path.join(SS, '31_formfill_target_hover.png') })
    const source = page.locator('text=Drop source files here').locator('..')
    await source.hover()
    await page.waitForTimeout(200)
    await page.screenshot({ path: path.join(SS, '32_formfill_source_hover.png') })
  })
})

test.describe('Schedules Interactions', () => {
  test('empty state with step guide', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.goto('/schedules')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(SS, '40_schedules_empty.png') })
  })
})

test.describe('Document Inbox Interactions', () => {
  test('inbox with docs and copy address', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.goto('/inbox')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.screenshot({ path: path.join(SS, '50_inbox_full.png') })
    const copyBtn = page.getByText('Copy')
    if (await copyBtn.isVisible()) {
      await copyBtn.click()
      await page.waitForTimeout(500)
      await page.screenshot({ path: path.join(SS, '51_inbox_copied.png') })
    }
  })

  test('select document shows action buttons', async ({ page }) => {
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
        if (data.state && data.state.user) {
          data.state.user.subscription_tier = 'free'
        }
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

  test('starter user sees upgrade prompt', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.evaluate(() => {
      const raw = localStorage.getItem('gridpull-auth-v5')
      if (raw) {
        const data = JSON.parse(raw)
        if (data.state && data.state.user) {
          data.state.user.subscription_tier = 'starter'
        }
        localStorage.setItem('gridpull-auth-v5', JSON.stringify(data))
      }
    })
    await page.goto('/proposals')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)
    await page.screenshot({ path: path.join(SS, '61_proposals_starter_gate.png'), fullPage: true })
    await expect(page.getByText('Proposals require a Pro plan')).toBeVisible()
  })

  test('pro user sees full proposals form', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.goto('/proposals')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(SS, '62_proposals_pro_full.png'), fullPage: true })
    await expect(page.getByRole('heading', { name: 'Proposals' })).toBeVisible()
  })

  test('LOB dropdown and client size toggle', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.goto('/proposals')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(500)
    const lobSelect = page.locator('#lob')
    await lobSelect.selectOption('cyber')
    await page.waitForTimeout(200)
    await page.screenshot({ path: path.join(SS, '63_proposals_cyber_lob.png') })
  })
})

test.describe('Pipelines Interactions', () => {
  test('pipelines list and new pipeline button', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.goto('/pipelines')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(SS, '70_pipelines_list.png') })
    const newBtn = page.getByText('New Pipeline')
    if (await newBtn.isVisible()) {
      await newBtn.click()
      await page.waitForTimeout(500)
      await page.screenshot({ path: path.join(SS, '71_pipelines_wizard.png') })
      await page.keyboard.press('Escape')
      await page.waitForTimeout(300)
    }
  })
})

test.describe('Settings Interactions', () => {
  test('all settings tabs', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(SS, '80_settings_subscription.png') })
    await page.getByText('Usage').click()
    await page.waitForTimeout(1000)
    await page.screenshot({ path: path.join(SS, '81_settings_usage.png') })
    await page.getByText('Profile').click()
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(SS, '82_settings_profile.png') })
  })

  test('no presets tab visible', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(500)
    await expect(page.locator('button:has-text("Presets")')).not.toBeVisible()
    await expect(page.locator('button:has-text("Defaults")')).not.toBeVisible()
    await page.screenshot({ path: path.join(SS, '83_settings_no_presets.png') })
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
        if (data.state && data.state.user) {
          data.state.user.subscription_tier = 'free'
        }
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
