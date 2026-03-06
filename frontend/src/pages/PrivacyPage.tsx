import { FileSpreadsheet, Shield, Lock, Trash2, Eye, ServerCrash, KeyRound, ShieldCheck } from 'lucide-react'
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
          <h1 className="text-3xl font-bold tracking-tight mb-2">Privacy & Security</h1>
          <p className="text-muted-foreground text-sm mb-4">Last updated: March 2026</p>
          <p className="text-muted-foreground text-sm mb-10 leading-relaxed">
            We understand that the documents you upload — invoices, financial reports, contracts — may contain
            sensitive information. This page explains exactly how your data is handled, protected, and deleted.
            We've written it in plain language so there's no ambiguity about what happens to your files.
          </p>

          {/* Security summary cards */}
          <div className="grid sm:grid-cols-2 gap-4 mb-12">
            {[
              { icon: Lock, title: 'Encrypted transfers', desc: 'All uploads and downloads use TLS/HTTPS encryption.' },
              { icon: Trash2, title: 'Files deleted after use', desc: 'Documents are processed in memory and permanently deleted after extraction.' },
              { icon: Eye, title: 'No human access', desc: 'Your files are processed entirely by AI. No person ever sees your documents.' },
              { icon: ServerCrash, title: 'Not used for AI training', desc: 'Your documents are never used to train, fine-tune, or improve any AI model.' },
              { icon: KeyRound, title: 'No third-party sharing', desc: 'We never sell, share, or provide your data to anyone.' },
              { icon: ShieldCheck, title: 'You control your data', desc: 'Request deletion of your account and all data at any time.' },
            ].map((item) => (
              <div key={item.title} className="flex gap-3 p-4 bg-card border border-border rounded-xl">
                <div className="w-8 h-8 bg-emerald-500/10 rounded-lg flex items-center justify-center flex-shrink-0">
                  <item.icon size={15} className="text-emerald-600" />
                </div>
                <div>
                  <p className="text-sm font-medium mb-0.5">{item.title}</p>
                  <p className="text-xs text-muted-foreground">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="space-y-8 text-sm leading-relaxed">
            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                1. What We Collect
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>
                  When you sign in with Google, we receive your email address, display name, and profile
                  picture through Google OAuth. <strong>We do not collect or store passwords.</strong>
                </p>
                <p>
                  We also store basic usage data — the number of documents you've processed and your account
                  balance — to calculate billing. We do not track your browsing activity, and we do not use
                  third-party analytics or advertising trackers.
                </p>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                2. How We Use Your Data
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>
                  Your account information (email, name) is used solely for authentication and billing.
                </p>
                <p>
                  Documents you upload are processed in memory to perform AI-powered data extraction. They are
                  <strong> not stored permanently on our servers</strong>. Extracted results are returned to
                  you and then removed from our systems.
                </p>
                <p>
                  We do not use your data for marketing, profiling, or any purpose other than providing the
                  extraction service you requested.
                </p>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                3. Document Handling & Processing
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>
                  This is the most important section if you're concerned about sensitive documents.
                  Here's exactly what happens when you upload a file:
                </p>
                <ol className="list-decimal list-inside space-y-2 pl-1">
                  <li>Your file is uploaded over an encrypted HTTPS connection.</li>
                  <li>The document is processed in memory — it is not written to permanent disk storage.</li>
                  <li>The content is sent to our AI processing service for data extraction.</li>
                  <li>The extracted field values (e.g., "Invoice Number: 12345") are returned to you.</li>
                  <li>Your original document is permanently deleted from memory immediately after extraction.</li>
                </ol>
                <p>
                  Extracted data (field values only, not the original document) may be temporarily cached during
                  your active session so you can view and download your results. This cache is cleared when your
                  session ends.
                </p>
                <p>
                  <strong>At no point is your original document stored on disk, backed up, or retained.</strong>
                </p>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                4. AI Processing & Model Training
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>
                  <strong>Your documents are never used to train, fine-tune, or improve any AI model.</strong>
                </p>
                <p>
                  We use AI services to read and extract data from your documents. The content of your documents
                  is sent to these services only for the purpose of performing extraction — and is not retained
                  by those services for model training or any other purpose.
                </p>
                <p>
                  We work with AI providers whose terms explicitly state that customer data submitted through
                  their API is not used for model training.
                </p>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                5. Third-Party Services
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>We use the following third-party services:</p>
                <ul className="list-disc list-inside space-y-1 pl-1">
                  <li><strong>Google OAuth</strong> — for secure sign-in (we only receive your name, email, and profile picture)</li>
                  <li><strong>AI processing APIs</strong> — for document extraction and OCR (your documents are processed but not stored or used for training)</li>
                  <li><strong>Stripe</strong> — for secure payment processing (we never see or store your full credit card number)</li>
                </ul>
                <p>
                  Each service is bound by its own privacy policy and data handling practices. We have selected
                  providers that meet our standards for data protection and do not use customer data for model training.
                </p>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                6. Data Selling & Sharing
              </h2>
              <p className="text-muted-foreground">
                <strong>We do not sell, rent, trade, or share your personal information or document contents
                with any third party.</strong> Not now, not ever. Your data is used solely to provide the
                extraction service you requested.
              </p>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                7. Cookies & Tracking
              </h2>
              <p className="text-muted-foreground">
                We use session-only cookies and localStorage to keep you signed in. <strong>We do not use
                third-party tracking cookies, analytics scripts, or advertising pixels.</strong> We do not
                track your activity across other websites.
              </p>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                8. Data Retention & Deletion
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>
                  <strong>Uploaded documents:</strong> Deleted immediately after extraction. Not stored on disk.
                </p>
                <p>
                  <strong>Extracted results:</strong> Temporarily cached during your session, then cleared.
                </p>
                <p>
                  <strong>Account data:</strong> Your email, name, and balance history are retained while your
                  account is active.
                </p>
                <p>
                  <strong>Deletion requests:</strong> You may request complete deletion of your account and all
                  associated data at any time by emailing{' '}
                  <a href="mailto:privacy@pdfexcel.ai" className="text-primary underline">
                    privacy@pdfexcel.ai
                  </a>
                  . We will process deletion requests within 30 days.
                </p>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                9. Security Measures
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>We protect your data with the following measures:</p>
                <ul className="list-disc list-inside space-y-1 pl-1">
                  <li>All data is transmitted over HTTPS with TLS encryption</li>
                  <li>Documents are processed in isolated memory — not stored on disk</li>
                  <li>API keys and credentials are stored as environment variables and never exposed to clients</li>
                  <li>Authentication uses secure OAuth 2.0 and JWT tokens</li>
                  <li>Payment processing is handled entirely by Stripe (PCI-compliant)</li>
                  <li>No third-party tracking or analytics scripts</li>
                </ul>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                10. For Businesses & Teams
              </h2>
              <div className="text-muted-foreground space-y-3">
                <p>
                  If your organization requires additional security measures, compliance documentation, or
                  a private deployment where no data leaves your network, please contact us at{' '}
                  <a href="mailto:contact@pdfexcel.ai" className="text-primary underline">
                    contact@pdfexcel.ai
                  </a>
                  .
                </p>
                <p>
                  We offer dedicated infrastructure deployments for enterprise teams with strict data handling
                  requirements.
                </p>
              </div>
            </section>

            <section>
              <h2 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Shield size={16} className="text-primary" />
                11. Contact
              </h2>
              <p className="text-muted-foreground">
                For privacy-related questions, data deletion requests, or security inquiries, contact us at{' '}
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
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 bg-primary rounded-md flex items-center justify-center">
              <FileSpreadsheet size={11} className="text-white" />
            </div>
            PDF to Excel
          </div>
          <div className="flex items-center gap-4">
            <Link to="/" className="hover:text-foreground transition-colors">Home</Link>
            <a href="mailto:contact@pdfexcel.ai" className="hover:text-foreground transition-colors">Contact</a>
            <span>© 2026 PDF to Excel. All rights reserved.</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
