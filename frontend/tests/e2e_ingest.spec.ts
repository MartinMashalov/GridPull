/**
 * Comprehensive end-to-end tests for the Document Inbox / Ingest pipeline.
 *
 * Tests cover:
 *  - Address management (create, get)
 *  - Direct upload (single, batch, empty, grouping)
 *  - Consumer vs business domain grouping
 *  - Mobile upload session lifecycle (create, validate, upload, invalid/expired token)
 *  - Document deletion (existing + non-existent)
 *  - Expiration filtering
 *  - Auth enforcement on all protected endpoints
 *  - Inbox UI elements (authenticated)
 */

import { test, expect } from '@playwright/test'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const SS = path.join(__dirname, '..', 'test-screenshots')

// ── Helpers ──────────────────────────────────────────────────────────────────

async function getAuthToken(request: any): Promise<string> {
  const resp = await request.post('/api/auth/dev-login', {
    data: { secret: 'gridpull-dev-bypass-2026' },
  })
  expect(resp.status()).toBe(200)
  const data = await resp.json()
  return data.access_token
}

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` }
}

function minimalPdf(tag = ''): Buffer {
  const content =
    '%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n' +
    '2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n' +
    '3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n' +
    'xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n' +
    '0000000058 00000 n \n0000000115 00000 n \n' +
    `trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF ${tag}`
  return Buffer.from(content)
}

// ── Auth enforcement ─────────────────────────────────────────────────────────

test.describe('Ingest - Auth enforcement', () => {
  test('inbox requires auth', async ({ request }) => {
    const resp = await request.get('/api/ingest/inbox')
    expect([401, 403]).toContain(resp.status())
  })

  test('address requires auth', async ({ request }) => {
    const resp = await request.get('/api/ingest/address')
    expect([401, 403]).toContain(resp.status())
  })

  test('upload requires auth', async ({ request }) => {
    const resp = await request.post('/api/ingest/inbox/upload')
    expect([401, 403, 422]).toContain(resp.status())
  })

  test('mobile-session create requires auth', async ({ request }) => {
    const resp = await request.post('/api/ingest/mobile-session', {
      data: {},
    })
    expect([401, 403]).toContain(resp.status())
  })
})

// ── Address management ───────────────────────────────────────────────────────

test.describe('Ingest - Address', () => {
  test('returns documents@gridpull.com as ingest address', async ({ request }) => {
    const token = await getAuthToken(request)
    const resp = await request.get('/api/ingest/address', {
      headers: authHeaders(token),
    })
    expect(resp.status()).toBe(200)
    const data = await resp.json()
    expect(data.address).toBe('documents@gridpull.com')
    expect(data.address_key).toBeTruthy()
  })
})

// ── Direct upload ────────────────────────────────────────────────────────────

test.describe('Ingest - Direct upload', () => {
  test('empty file is rejected (count=0)', async ({ request }) => {
    const token = await getAuthToken(request)
    const resp = await request.post('/api/ingest/inbox/upload', {
      headers: authHeaders(token),
      multipart: {
        files: { name: 'empty.pdf', mimeType: 'application/pdf', buffer: Buffer.alloc(0) },
        sender_email: 'empty-test@example.com',
      },
    })
    expect(resp.status()).toBe(200)
    const data = await resp.json()
    expect(data.count).toBe(0)
  })

  test('single file upload succeeds', async ({ request }) => {
    const token = await getAuthToken(request)
    const resp = await request.post('/api/ingest/inbox/upload', {
      headers: authHeaders(token),
      multipart: {
        files: { name: 'single_test.pdf', mimeType: 'application/pdf', buffer: minimalPdf('single') },
        sender_email: 'single-test@testcorp.com',
      },
    })
    expect(resp.status()).toBe(200)
    const data = await resp.json()
    expect(data.count).toBe(1)
    expect(data.uploaded[0].filename).toBe('single_test.pdf')

    // Clean up
    await request.delete(`/api/ingest/inbox/${data.uploaded[0].id}`, {
      headers: authHeaders(token),
    })
  })

  test('batch upload (2 files) succeeds', async ({ request }) => {
    const token = await getAuthToken(request)

    // Playwright multipart only allows one 'files' key per call, so we upload twice
    const resp1 = await request.post('/api/ingest/inbox/upload', {
      headers: authHeaders(token),
      multipart: {
        files: { name: 'batch_1.pdf', mimeType: 'application/pdf', buffer: minimalPdf('b1') },
        sender_email: 'batch@testcorp.com',
      },
    })
    const resp2 = await request.post('/api/ingest/inbox/upload', {
      headers: authHeaders(token),
      multipart: {
        files: { name: 'batch_2.pdf', mimeType: 'application/pdf', buffer: minimalPdf('b2') },
        sender_email: 'batch@testcorp.com',
      },
    })
    expect(resp1.status()).toBe(200)
    expect(resp2.status()).toBe(200)
    const d1 = await resp1.json()
    const d2 = await resp2.json()
    expect(d1.count).toBe(1)
    expect(d2.count).toBe(1)

    // Verify both appear in inbox under same business-domain group
    const inbox = await request.get('/api/ingest/inbox', { headers: authHeaders(token) })
    const inboxData = await inbox.json()
    const group = inboxData.groups.find((g: { sender_display: string }) => g.sender_display === 'testcorp.com')
    expect(group).toBeTruthy()
    expect(group.count).toBeGreaterThanOrEqual(2)

    // Clean up
    await request.delete(`/api/ingest/inbox/${d1.uploaded[0].id}`, { headers: authHeaders(token) })
    await request.delete(`/api/ingest/inbox/${d2.uploaded[0].id}`, { headers: authHeaders(token) })
  })
})

// ── Domain grouping ──────────────────────────────────────────────────────────

test.describe('Ingest - Domain grouping', () => {
  test('consumer domain (gmail) groups by full email', async ({ request }) => {
    const token = await getAuthToken(request)
    const resp = await request.post('/api/ingest/inbox/upload', {
      headers: authHeaders(token),
      multipart: {
        files: { name: 'consumer_test.pdf', mimeType: 'application/pdf', buffer: minimalPdf('consumer') },
        sender_email: 'jane@gmail.com',
      },
    })
    const data = await resp.json()
    expect(data.count).toBe(1)

    const inbox = await request.get('/api/ingest/inbox', { headers: authHeaders(token) })
    const inboxData = await inbox.json()
    const group = inboxData.groups.find((g: { sender_display: string }) => g.sender_display === 'jane@gmail.com')
    expect(group).toBeTruthy()

    await request.delete(`/api/ingest/inbox/${data.uploaded[0].id}`, { headers: authHeaders(token) })
  })

  test('business domain groups by domain, merging senders', async ({ request }) => {
    const token = await getAuthToken(request)
    const r1 = await request.post('/api/ingest/inbox/upload', {
      headers: authHeaders(token),
      multipart: {
        files: { name: 'biz_alice.pdf', mimeType: 'application/pdf', buffer: minimalPdf('alice') },
        sender_email: 'alice@acme-ins.com',
      },
    })
    const r2 = await request.post('/api/ingest/inbox/upload', {
      headers: authHeaders(token),
      multipart: {
        files: { name: 'biz_bob.pdf', mimeType: 'application/pdf', buffer: minimalPdf('bob') },
        sender_email: 'bob@acme-ins.com',
      },
    })
    const d1 = await r1.json()
    const d2 = await r2.json()

    const inbox = await request.get('/api/ingest/inbox', { headers: authHeaders(token) })
    const inboxData = await inbox.json()
    const group = inboxData.groups.find((g: { sender_display: string }) => g.sender_display === 'acme-ins.com')
    expect(group).toBeTruthy()
    expect(group.count).toBe(2)

    await request.delete(`/api/ingest/inbox/${d1.uploaded[0].id}`, { headers: authHeaders(token) })
    await request.delete(`/api/ingest/inbox/${d2.uploaded[0].id}`, { headers: authHeaders(token) })
  })
})

// ── Mobile upload session ────────────────────────────────────────────────────

test.describe('Ingest - Mobile upload', () => {
  test('create session returns token and URL', async ({ request }) => {
    const token = await getAuthToken(request)
    const resp = await request.post('/api/ingest/mobile-session', {
      headers: authHeaders(token),
      data: { sender_email: 'mobile@agency.com', sender_domain: 'agency.com' },
    })
    expect(resp.status()).toBe(200)
    const data = await resp.json()
    expect(data.token).toBeTruthy()
    expect(data.url).toContain('/upload/')
    expect(data.expires_at).toBeTruthy()
  })

  test('validate valid token succeeds', async ({ request }) => {
    const token = await getAuthToken(request)
    const session = await (await request.post('/api/ingest/mobile-session', {
      headers: authHeaders(token),
      data: {},
    })).json()

    const resp = await request.get(`/api/ingest/mobile-session/${session.token}`)
    expect(resp.status()).toBe(200)
    const data = await resp.json()
    expect(data.valid).toBe(true)
  })

  test('validate bogus token returns 404', async ({ request }) => {
    const resp = await request.get('/api/ingest/mobile-session/totally-invalid-token')
    expect(resp.status()).toBe(404)
  })

  test('upload via mobile token succeeds without auth', async ({ request }) => {
    const token = await getAuthToken(request)
    const session = await (await request.post('/api/ingest/mobile-session', {
      headers: authHeaders(token),
      data: { sender_email: 'mob-upload@agency.com', sender_domain: 'agency.com' },
    })).json()

    // Upload without auth header - only token in URL
    const resp = await request.post(`/api/ingest/mobile-upload/${session.token}`, {
      multipart: {
        file: { name: 'mobile_doc.pdf', mimeType: 'application/pdf', buffer: minimalPdf('mobile') },
      },
    })
    expect(resp.status()).toBe(200)
    const data = await resp.json()
    expect(data.status).toBe('uploaded')
    expect(data.filename).toBe('mobile_doc.pdf')

    // Clean up
    await request.delete(`/api/ingest/inbox/${data.id}`, { headers: authHeaders(token) })
  })

  test('upload via invalid token returns 404', async ({ request }) => {
    const resp = await request.post('/api/ingest/mobile-upload/bogus-token', {
      multipart: {
        file: { name: 'fail.pdf', mimeType: 'application/pdf', buffer: minimalPdf() },
      },
    })
    expect(resp.status()).toBe(404)
  })
})

// ── Delete ───────────────────────────────────────────────────────────────────

test.describe('Ingest - Delete', () => {
  test('delete non-existent doc returns 404', async ({ request }) => {
    const token = await getAuthToken(request)
    const resp = await request.delete('/api/ingest/inbox/00000000-0000-0000-0000-000000000000', {
      headers: authHeaders(token),
    })
    expect(resp.status()).toBe(404)
  })

  test('delete existing doc returns success', async ({ request }) => {
    const token = await getAuthToken(request)
    // Upload then delete
    const upload = await request.post('/api/ingest/inbox/upload', {
      headers: authHeaders(token),
      multipart: {
        files: { name: 'delete_me.pdf', mimeType: 'application/pdf', buffer: minimalPdf('del') },
        sender_email: 'delete-test@example.com',
      },
    })
    const uploadData = await upload.json()
    expect(uploadData.count).toBe(1)

    const resp = await request.delete(`/api/ingest/inbox/${uploadData.uploaded[0].id}`, {
      headers: authHeaders(token),
    })
    expect(resp.status()).toBe(200)
    const data = await resp.json()
    expect(data.status).toBe('deleted')
  })
})

// ── Expiration ───────────────────────────────────────────────────────────────

test.describe('Ingest - Expiration', () => {
  test('all inbox documents have expiry dates', async ({ request }) => {
    const token = await getAuthToken(request)
    const resp = await request.get('/api/ingest/inbox', { headers: authHeaders(token) })
    const data = await resp.json()

    for (const group of data.groups) {
      for (const doc of group.documents) {
        expect(doc.expires_at).toBeTruthy()
        // Verify expiry is in the future
        const exp = new Date(doc.expires_at)
        expect(exp.getTime()).toBeGreaterThan(Date.now())
      }
    }
  })
})

// ── Authenticated UI ─────────────────────────────────────────────────────────

test.describe('Ingest - Inbox UI', () => {
  test('inbox page shows forwarding address and document groups', async ({ page }) => {
    await page.goto('/auto-login?t=gridpull-dev-bypass-2026')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)

    await page.goto('/inbox')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)

    // Page title
    await expect(page.getByRole('heading', { name: 'Document Inbox' })).toBeVisible()

    // Forwarding address card
    await expect(page.getByText('Forwarding Address')).toBeVisible()
    await expect(page.getByText('documents@gridpull.com').or(page.locator('code'))).toBeVisible()

    // Action buttons
    await expect(page.getByText('Upload Files')).toBeVisible()
    await expect(page.getByText('Refresh')).toBeVisible()

    // Document count badge
    await expect(page.locator('text=/\\d+ documents?/')).toBeVisible()

    // Guidance text
    await expect(page.getByText('Forward emails with attachments')).toBeVisible()

    await page.screenshot({ path: path.join(SS, 'ingest_inbox_full.png'), fullPage: true })
  })
})
