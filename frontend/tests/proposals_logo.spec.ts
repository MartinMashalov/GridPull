import { test, expect } from '@playwright/test'
import path from 'path'
import fs from 'fs'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const SS = path.join(__dirname, '..', 'test-screenshots', 'proposals_logo')
const L = '/auto-login?t=gridpull-dev-bypass-2026'

// Minimal 1x1 PNG — authenticates as an image for the backend without needing a real asset on disk.
const PNG_1x1 = Buffer.from(
  '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da6300010000000500010d0a2db40000000049454e44ae426082',
  'hex',
)

test.describe('Proposals — agency logo upload', () => {
  test.beforeAll(() => { fs.mkdirSync(SS, { recursive: true }) })

  test('upload + save logo persists across reloads', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')

    await page.goto('/proposals')
    await page.waitForLoadState('networkidle')
    await page.screenshot({ path: path.join(SS, '01_proposals_page.png'), fullPage: true })

    // The picker input is hidden; we set the file directly on it (matches Papyra's pattern).
    const logoInput = page.getByTestId('agency-logo-input')
    await logoInput.setInputFiles({
      name: 'test-logo.png',
      mimeType: 'image/png',
      buffer: PNG_1x1,
    })

    const pill = page.getByTestId('agency-logo-pill')
    await expect(pill).toBeVisible()
    await expect(pill).toContainText('test-logo.png')
    await page.screenshot({ path: path.join(SS, '02_logo_selected.png') })

    // Save — waits for the PUT /proposals/agency-info request to complete with 2xx.
    const [resp] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes('/proposals/agency-info') && r.request().method() === 'PUT',
        { timeout: 30000 },
      ),
      page.getByTestId('agency-save-btn').click(),
    ])
    expect(resp.status(), `Save response: ${await resp.text()}`).toBeLessThan(300)
    await page.screenshot({ path: path.join(SS, '03_after_save.png') })

    // Reload and confirm the saved logo filename is rehydrated from the server.
    await page.reload()
    await page.waitForLoadState('networkidle')
    await expect(page.getByTestId('agency-logo-pill')).toContainText('test-logo.png', { timeout: 15000 })
    await page.screenshot({ path: path.join(SS, '04_after_reload.png') })
  })

  test('rejects oversized logo client-side', async ({ page }) => {
    await page.goto(L)
    await page.waitForLoadState('networkidle')
    await page.goto('/proposals')
    await page.waitForLoadState('networkidle')

    const big = Buffer.alloc(3 * 1024 * 1024, 0xff) // 3 MB
    await page.getByTestId('agency-logo-input').setInputFiles({
      name: 'huge.png',
      mimeType: 'image/png',
      buffer: big,
    })
    // Pill should NOT show the rejected file.
    await expect(page.getByTestId('agency-logo-pill')).not.toContainText('huge.png')
  })
})
