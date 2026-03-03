import { FileSpreadsheet } from 'lucide-react'
import { Link } from 'react-router-dom'

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      {/* Navbar */}
      <header className="border-b border-border/50 backdrop-blur-sm sticky top-0 z-50 bg-background/80">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="w-7 h-7 bg-primary rounded-lg flex items-center justify-center">
              <FileSpreadsheet size={14} className="text-white" />
            </div>
            <span className="font-semibold text-sm tracking-tight">PDF to Excel</span>
          </Link>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1 py-16 px-6">
        <div className="max-w-3xl mx-auto">
          <h1 className="text-3xl font-bold tracking-tight mb-2">Privacy Policy</h1>
          <p className="text-muted-foreground text-sm mb-10">Last updated: March 2026</p>

          <div className="space-y-8 text-sm leading-relaxed">
            <section>
              <h2 className="font-semibold text-base mb-3">1. What We Collect</h2>
              <p className="text-muted-foreground">
                When you sign in with Google, we receive your email address, display name, and Google profile
                picture via OAuth. We do not collect passwords. Usage data (number of documents processed,
                token consumption) is stored to calculate billing.
              </p>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3">2. How We Use Your Data</h2>
              <p className="text-muted-foreground">
                Your account information is used solely for authentication and billing. Documents you upload
                are processed in memory to perform AI-powered data extraction and are not stored permanently
                on our servers. Extracted results are returned to you and deleted from our systems after
                delivery.
              </p>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3">3. Document Handling</h2>
              <p className="text-muted-foreground">
                Uploaded PDF files are processed in-memory and passed to AI models (OpenAI GPT-4.1-mini and
                Mistral OCR) for extraction. We do not store document contents after processing is complete.
                Extracted data (field values) may be temporarily cached to display results in your session.
              </p>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3">4. Third-Party Services</h2>
              <p className="text-muted-foreground">
                We use the following third-party services: Google OAuth for authentication, OpenAI API for
                text extraction, Mistral AI API for OCR on scanned documents, and Stripe for payment
                processing. Each service has its own privacy policy governing data handling.
              </p>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3">5. Data Selling</h2>
              <p className="text-muted-foreground">
                We do not sell, rent, or trade your personal information or document contents to any third
                party, ever.
              </p>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3">6. Cookies</h2>
              <p className="text-muted-foreground">
                We use session-only cookies and localStorage to maintain your authentication state. No
                third-party tracking cookies are used.
              </p>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3">7. Data Retention & Deletion</h2>
              <p className="text-muted-foreground">
                Account data (email, name, balance history) is retained while your account is active. You
                may request deletion of your account and all associated data at any time by emailing{' '}
                <a href="mailto:privacy@pdfexcel.ai" className="text-primary underline">
                  privacy@pdfexcel.ai
                </a>
                . We will process deletion requests within 30 days.
              </p>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3">8. Security</h2>
              <p className="text-muted-foreground">
                All data is transmitted over HTTPS. API keys and credentials are stored as environment
                variables and never exposed to clients. We follow industry-standard security practices to
                protect your data.
              </p>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3">9. Contact</h2>
              <p className="text-muted-foreground">
                For privacy-related questions or data deletion requests, contact us at{' '}
                <a href="mailto:privacy@pdfexcel.ai" className="text-primary underline">
                  privacy@pdfexcel.ai
                </a>
                .
              </p>
            </section>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border/50 py-6 px-6">
        <div className="max-w-6xl mx-auto flex items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 bg-primary rounded-md flex items-center justify-center">
              <FileSpreadsheet size={11} className="text-white" />
            </div>
            PDF to Excel
          </div>
          <div>© 2026 PDF to Excel. All rights reserved.</div>
        </div>
      </footer>
    </div>
  )
}
