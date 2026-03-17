import { FileSpreadsheet, Shield } from 'lucide-react'
import { Link } from 'react-router-dom'

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      {/* Navbar */}
      <header className="border-b border-border/50 backdrop-blur-sm sticky top-0 z-50 bg-background/80">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="w-7 h-7 bg-primary rounded-lg flex items-center justify-center">
              <FileSpreadsheet size={14} className="text-white" />
            </div>
            <span className="font-semibold text-sm tracking-tight">PDF to Excel</span>
          </Link>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1 py-10 sm:py-16 px-4 sm:px-6">
        <div className="max-w-3xl mx-auto">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight mb-2">Terms of Service</h1>
          <p className="text-muted-foreground text-sm mb-4">Last updated: March 2026</p>
          <p className="text-muted-foreground text-sm mb-10 leading-relaxed">
            These Terms of Service ("Terms") govern your use of PDFexcel.ai ("Service"), operated by
            Big Vision Systems LLC ("Company", "we", "us", or "our"). By accessing or using the Service,
            you agree to be bound by these Terms. If you do not agree, do not use the Service.
          </p>

          <div className="space-y-8 text-sm leading-relaxed">
            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                1. Description of Service
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>
                  PDFexcel.ai is an AI-powered document data extraction platform. The Service allows users to
                  upload PDF documents and other supported file types, select data fields to extract, and
                  receive structured spreadsheet output (Excel or CSV).
                </p>
                <p>
                  The Service is provided on a pay-per-use basis. Users add funds to their account balance,
                  which is consumed as documents are processed.
                </p>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                2. Eligibility
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>
                  You must be at least 18 years old to use this Service. By using the Service, you represent
                  and warrant that you are at least 18 years of age and have the legal capacity to enter into
                  these Terms.
                </p>
                <p>
                  If you are using the Service on behalf of an organization, you represent that you have the
                  authority to bind that organization to these Terms.
                </p>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                3. Account Registration
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>
                  To use the Service, you must sign in using Google OAuth. You are responsible for maintaining
                  the security of your Google account and for all activity that occurs under your account on
                  the Service.
                </p>
                <p>
                  You agree to provide accurate information and to promptly update your account if any
                  information changes. We reserve the right to suspend or terminate accounts that violate
                  these Terms.
                </p>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                4. Acceptable Use
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>You agree not to use the Service to:</p>
                <ul className="list-disc list-inside space-y-1 pl-1">
                  <li>Upload documents containing illegal content or content that infringes on the intellectual property rights of others</li>
                  <li>Attempt to reverse-engineer, decompile, or extract the source code or algorithms of the Service</li>
                  <li>Use automated bots, scrapers, or similar tools to access the Service without our permission</li>
                  <li>Interfere with, disrupt, or overload the Service's infrastructure</li>
                  <li>Resell, redistribute, or sublicense the Service without written authorization</li>
                  <li>Use the Service for any purpose that violates applicable law or regulation</li>
                </ul>
                <p>
                  We reserve the right to suspend or terminate your access if we reasonably believe you have
                  violated these terms.
                </p>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                5. Payments & Billing
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>
                  The Service operates on a prepaid balance model. You add funds to your account, and charges
                  are deducted as you process documents. All payments are processed securely through Stripe.
                </p>
                <p>
                  <strong>No subscriptions:</strong> There are no recurring charges unless you explicitly enable
                  the auto-renewal feature, which tops up your balance when it falls below a threshold you set.
                </p>
                <p>
                  <strong>Refunds:</strong> Account balances are non-refundable except where required by law or
                  in cases of Service malfunction that resulted in incorrect charges. To request a refund,
                  contact us at{' '}
                  <a href="mailto:bigvisionsystems@gmail.com" className="text-primary underline">
                    bigvisionsystems@gmail.com
                  </a>.
                </p>
                <p>
                  <strong>Balance expiry:</strong> Account balances do not expire.
                </p>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                6. Intellectual Property
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>
                  <strong>Your content:</strong> You retain all rights to documents you upload and data you extract.
                  We do not claim ownership over your documents or extracted data.
                </p>
                <p>
                  <strong>Our service:</strong> The Service, including its design, code, algorithms, and branding,
                  is the property of Big Vision Systems LLC and is protected by intellectual property laws. You may
                  not copy, modify, or distribute any part of the Service without our written consent.
                </p>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                7. Data Handling & Privacy
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>
                  Your use of the Service is also governed by our{' '}
                  <Link to="/privacy" className="text-primary underline">Privacy Policy</Link>, which describes
                  how we collect, use, and protect your data. Key points:
                </p>
                <ul className="list-disc list-inside space-y-1 pl-1">
                  <li>Documents are processed in memory and deleted immediately after extraction</li>
                  <li>Your documents are never used to train AI models</li>
                  <li>We do not sell or share your data with third parties</li>
                  <li>All transfers are encrypted using TLS/HTTPS</li>
                </ul>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                8. Service Accuracy & Disclaimer
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>
                  The Service uses AI to extract data from documents. While we strive for high accuracy (99%+
                  on real-world documents), <strong>we do not guarantee that extraction results will be 100%
                  accurate or error-free</strong>.
                </p>
                <p>
                  You are responsible for reviewing extracted data before using it for business, legal, financial,
                  or other critical decisions. The Service is provided "as is" and "as available" without warranties
                  of any kind, express or implied, including but not limited to warranties of merchantability,
                  fitness for a particular purpose, and non-infringement.
                </p>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                9. Limitation of Liability
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>
                  To the maximum extent permitted by law, Big Vision Systems LLC and its officers, directors,
                  employees, and agents shall not be liable for any indirect, incidental, special, consequential,
                  or punitive damages, including but not limited to loss of profits, data, or business opportunities,
                  arising out of or related to your use of the Service.
                </p>
                <p>
                  Our total liability for any claims arising from your use of the Service is limited to the
                  amount you have paid to us in the 12 months preceding the claim.
                </p>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                10. Indemnification
              </h2>
              <p className="text-muted-foreground">
                You agree to indemnify, defend, and hold harmless Big Vision Systems LLC from any claims,
                liabilities, damages, losses, and expenses (including reasonable attorney's fees) arising
                from your use of the Service, your violation of these Terms, or your violation of any rights
                of a third party.
              </p>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                11. Modifications to the Service & Terms
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>
                  We reserve the right to modify, suspend, or discontinue the Service (or any part of it)
                  at any time, with or without notice.
                </p>
                <p>
                  We may update these Terms from time to time. If we make material changes, we will notify you
                  by updating the "Last updated" date at the top of this page. Your continued use of the Service
                  after changes are posted constitutes your acceptance of the revised Terms.
                </p>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                12. Termination
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>
                  You may stop using the Service at any time. You may request deletion of your account and
                  all associated data by contacting us.
                </p>
                <p>
                  We may suspend or terminate your access to the Service at any time for violation of these
                  Terms, or for any reason at our discretion with reasonable notice.
                </p>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                13. Governing Law & Dispute Resolution
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>
                  These Terms are governed by and construed in accordance with the laws of the State of Delaware,
                  United States, without regard to its conflict of law provisions.
                </p>
                <p>
                  Any disputes arising from these Terms or the Service shall be resolved through binding
                  arbitration in accordance with the rules of the American Arbitration Association, unless
                  you are seeking injunctive or other equitable relief in a court of competent jurisdiction.
                </p>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                14. Contact
              </h2>
              <p className="text-muted-foreground">
                For questions about these Terms, contact us at{' '}
                <a href="mailto:bigvisionsystems@gmail.com" className="text-primary underline">
                  bigvisionsystems@gmail.com
                </a>.
              </p>
            </section>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border/50 py-6 px-4 sm:px-6">
        <div className="max-w-6xl mx-auto flex flex-col items-center gap-3 text-xs text-muted-foreground text-center">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 bg-primary rounded-md flex items-center justify-center">
              <FileSpreadsheet size={11} className="text-white" />
            </div>
            PDF to Excel
          </div>
          <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1">
            <Link to="/" className="hover:text-foreground transition-colors">Home</Link>
            <Link to="/privacy" className="hover:text-foreground transition-colors">Privacy Policy</Link>
            <a href="mailto:bigvisionsystems@gmail.com" className="hover:text-foreground transition-colors">Contact</a>
          </div>
          <span>© 2026 Big Vision Systems LLC. All rights reserved.</span>
        </div>
      </footer>
    </div>
  )
}
