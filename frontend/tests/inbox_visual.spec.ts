import { test, expect } from '@playwright/test'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const SS = path.join(__dirname, '..', 'test-screenshots')

test('capture authenticated inbox page', async ({ page }) => {
  await page.goto('/auto-login?t=gridpull-dev-bypass-2026')
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(2000)

  await page.goto('/inbox')
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(2000)

  // Use heading to avoid strict mode
  await expect(page.getByRole('heading', { name: 'Document Inbox' })).toBeVisible()
  await expect(page.getByText('Forwarding Address')).toBeVisible()

  await page.screenshot({ path: path.join(SS, 'inbox_authenticated.png'), fullPage: true })
})

test('capture authenticated form-filling page', async ({ page }) => {
  await page.goto('/auto-login?t=gridpull-dev-bypass-2026')
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(2000)

  await page.goto('/form-filling')
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(1000)

  await expect(page.getByRole('heading', { name: 'Form Filling' })).toBeVisible()
  await page.screenshot({ path: path.join(SS, 'formfilling_authenticated.png'), fullPage: true })
})

test('capture authenticated settings page (no presets)', async ({ page }) => {
  await page.goto('/auto-login?t=gridpull-dev-bypass-2026')
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(2000)

  await page.goto('/settings')
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(1000)

  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
  // Verify NO presets tab exists
  await expect(page.locator('text=Presets')).not.toBeVisible()
  await expect(page.locator('[value="defaults"]')).not.toBeVisible()

  await page.screenshot({ path: path.join(SS, 'settings_authenticated.png'), fullPage: true })
})

test('sidebar shows correct navigation items', async ({ page }) => {
  await page.goto('/auto-login?t=gridpull-dev-bypass-2026')
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(2000)

  await page.goto('/form-filling')
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(1000)

  const sidebar = page.locator('aside')
  await expect(sidebar.getByText('Form Filling')).toBeVisible()
  await expect(sidebar.getByText('Schedules')).toBeVisible()
  await expect(sidebar.getByText('Document Inbox')).toBeVisible()
  await expect(sidebar.getByText('Proposals')).toBeVisible()
  await expect(sidebar.getByText('Pipelines')).toBeVisible()
  await expect(sidebar.getByText('Settings')).toBeVisible()
  // No Dashboard in sidebar
  await expect(sidebar.locator('text=Dashboard')).not.toBeVisible()

  await page.screenshot({ path: path.join(SS, 'sidebar_authenticated.png') })
})
