import { test, expect, type Page } from '@playwright/test'
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

async function login(page: Page) {
  await page.goto(L)
  // Auto-login redirects off /auto-login once the dev-login POST resolves; wait for any other URL
  await page.waitForURL((u) => !u.toString().includes('/auto-login'), { timeout: 20000 })
  // Auth is persisted to localStorage by Zustand (key: gridpull-auth-v5), not cookies
  const token = await page.evaluate(() => {
    const raw = localStorage.getItem('gridpull-auth-v5')
    if (!raw) return null
    try { return JSON.parse(raw)?.state?.token ?? null } catch { return null }
  })
  expect(token, 'Auto-login did not persist an access token to gridpull-auth-v5').toBeTruthy()
}

async function gotoProposals(page: Page) {
  await page.goto('/proposals')
  // Anchor on the save button rather than networkidle — survives background polling
  await expect(page.getByTestId('agency-save-btn')).toBeVisible({ timeout: 20000 })
}

test.describe('Proposals — agency logo upload', () => {
  test.beforeAll(() => { fs.mkdirSync(SS, { recursive: true }) })

  test('upload + save logo persists across reloads', async ({ page }) => {
    await login(page)
    await gotoProposals(page)
    await page.screenshot({ path: path.join(SS, '01_proposals_page.png'), fullPage: true })

    // Unique filename per run so the after-reload assertion can't pass from prior runs
    const uniqueName = `logo-${Date.now()}.png`

    // Fill agency info so the Papyra content field is a deterministic non-empty value
    const agencyText = `Test Agency ${Date.now()}`
    const textarea = page.locator('#agency-info')
    await expect(textarea).toBeVisible({ timeout: 15000 })
    await textarea.fill(agencyText)

    const logoInput = page.getByTestId('agency-logo-input')
    await logoInput.setInputFiles({
      name: uniqueName,
      mimeType: 'image/png',
      buffer: PNG_1x1,
    })

    const pill = page.getByTestId('agency-logo-pill')
    await expect(pill).toBeVisible()
    await expect(pill).toContainText(uniqueName)

    // Visual proof: the picked file renders as an actual image (naturalWidth > 0 means decoded bytes)
    const previewPre = page.getByTestId('agency-logo-preview')
    await expect(previewPre).toBeVisible()
    await previewPre.evaluate((el: HTMLImageElement) =>
      el.complete ? null : new Promise(r => { el.onload = () => r(null); el.onerror = () => r(null) }),
    )
    expect(
      await previewPre.evaluate((el: HTMLImageElement) => el.naturalWidth),
      'Pre-save preview did not decode',
    ).toBeGreaterThan(0)
    await page.screenshot({ path: path.join(SS, '02_logo_selected.png') })

    // Save — wait for the PUT and assert on response body, not just status range
    const [resp] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes('/proposals/agency-info') && r.request().method() === 'PUT',
        { timeout: 30000 },
      ),
      page.getByTestId('agency-save-btn').click(),
    ])
    const respText = await resp.text()
    expect(resp.status(), `PUT non-2xx (body=${respText.slice(0, 400)})`).toBe(200)

    // UI should reflect a successful save (toast)
    await expect(page.getByText(/Agency info saved/i)).toBeVisible({ timeout: 10000 })
    await page.screenshot({ path: path.join(SS, '03_after_save.png') })

    // Independent verification: GET returns the same filename + non-empty logo bytes before we trust the reload.
    // Auth is localStorage-based, so fetch through the page context to pick up the Bearer token via axios.
    const getBody = await page.evaluate(async () => {
      const raw = localStorage.getItem('gridpull-auth-v5')
      const tok = raw ? JSON.parse(raw)?.state?.token : null
      const r = await fetch('/api/proposals/agency-info', { headers: tok ? { Authorization: `Bearer ${tok}` } : {} })
      return { status: r.status, body: await r.json().catch(() => null) }
    })
    expect(getBody.status, `GET after save: ${getBody.status}`).toBe(200)
    expect(getBody.body?.logo_filename, `GET body: ${JSON.stringify(getBody.body)}`).toBe(uniqueName)
    expect(
      typeof getBody.body?.logo_base64 === 'string' && getBody.body.logo_base64.length > 0,
      `GET after save missing logo_base64: ${JSON.stringify(getBody.body).slice(0, 200)}`,
    ).toBe(true)

    // Reload and confirm rehydrated state comes from the server, not stale in-memory state
    await page.reload()
    await expect(page.getByTestId('agency-save-btn')).toBeVisible({ timeout: 20000 })
    await expect(page.getByTestId('agency-logo-pill')).toContainText(uniqueName, { timeout: 15000 })

    // Visual proof post-reload: server-served bytes decoded into a real image (not a broken <img>)
    const previewPost = page.getByTestId('agency-logo-preview')
    await expect(previewPost).toBeVisible()
    await previewPost.evaluate((el: HTMLImageElement) =>
      el.complete ? null : new Promise(r => { el.onload = () => r(null); el.onerror = () => r(null) }),
    )
    expect(
      await previewPost.evaluate((el: HTMLImageElement) => el.naturalWidth),
      'Post-reload preview did not decode — bytes did not round-trip',
    ).toBeGreaterThan(0)
    await page.screenshot({ path: path.join(SS, '04_after_reload.png') })
  })

  test('rejects oversized logo client-side without firing a PUT', async ({ page }) => {
    await login(page)
    await gotoProposals(page)

    // Capture any agency-info PUT to prove the handler didn't fire
    let putFired = false
    page.on('request', (r) => {
      if (r.url().includes('/proposals/agency-info') && r.method() === 'PUT') putFired = true
    })

    const big = Buffer.alloc(3 * 1024 * 1024, 0xff) // 3 MB
    await page.getByTestId('agency-logo-input').setInputFiles({
      name: 'huge.png',
      mimeType: 'image/png',
      buffer: big,
    })

    // Error toast must surface
    await expect(page.getByText(/Logo must be under 2 MB/i)).toBeVisible({ timeout: 5000 })

    // Pill should not reflect the rejected file
    await expect(page.getByTestId('agency-logo-pill')).not.toContainText('huge.png')

    // Also verify no network save happened from the rejection (guard against silent success)
    await page.waitForTimeout(500)
    expect(putFired, 'Oversized logo unexpectedly triggered a PUT /proposals/agency-info').toBe(false)
  })

  test('rejects wrong mime type (e.g. application/pdf) client-side', async ({ page }) => {
    await login(page)
    await gotoProposals(page)

    let putFired = false
    page.on('request', (r) => {
      if (r.url().includes('/proposals/agency-info') && r.method() === 'PUT') putFired = true
    })

    await page.getByTestId('agency-logo-input').setInputFiles({
      name: 'bad.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.4 fake'),
    })

    await expect(page.getByText(/Logo must be PNG or JPG/i)).toBeVisible({ timeout: 5000 })
    await expect(page.getByTestId('agency-logo-pill')).not.toContainText('bad.pdf')
    await page.waitForTimeout(500)
    expect(putFired, 'Invalid mime unexpectedly triggered a PUT').toBe(false)
  })
})
