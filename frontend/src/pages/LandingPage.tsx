import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGoogleLogin } from '@react-oauth/google'
import { FileSpreadsheet, Zap, Shield, ArrowRight } from 'lucide-react'
import api from '@/lib/api'
import { useAuthStore } from '@/store/authStore'
import toast from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

const FEATURES = [
  {
    icon: Zap,
    title: 'AI-Powered Extraction',
    desc: 'GPT-4 reads and understands any PDF structure — invoices, reports, contracts, and more.',
  },
  {
    icon: FileSpreadsheet,
    title: 'Perfect Spreadsheets',
    desc: 'Structured Excel or CSV output with every field exactly where you need it.',
  },
  {
    icon: Shield,
    title: 'Enterprise Accuracy',
    desc: '94%+ field fill rate tested across thousands of real-world documents.',
  },
]

export default function LandingPage() {
  const navigate = useNavigate()
  const { setUser, user } = useAuthStore()
  const [loading, setLoading] = useState(false)

  const googleLogin = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      setLoading(true)
      try {
        const res = await api.post('/auth/google', {
          access_token: tokenResponse.access_token,
        })
        setUser(res.data.user, res.data.access_token)
        navigate('/dashboard')
      } catch (err) {
        toast.error('Login failed. Please try again.')
      } finally {
        setLoading(false)
      }
    },
    onError: () => toast.error('Google login failed'),
  })

  if (user) {
    navigate('/dashboard')
    return null
  }

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      {/* Navbar */}
      <header className="border-b border-border/50 backdrop-blur-sm sticky top-0 z-50 bg-background/80">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 bg-primary rounded-lg flex items-center justify-center">
              <FileSpreadsheet size={14} className="text-white" />
            </div>
            <span className="font-semibold text-sm tracking-tight">PDF to Excel</span>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => googleLogin()}
            disabled={loading}
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <div className="w-3.5 h-3.5 border-2 border-border border-t-foreground rounded-full animate-spin" />
                Signing in…
              </span>
            ) : (
              <>Sign in <ArrowRight size={13} /></>
            )}
          </Button>
        </div>
      </header>

      {/* Hero */}
      <section className="flex-1 flex flex-col items-center justify-center px-6 py-24 text-center relative overflow-hidden">
        {/* Subtle glow */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-[600px] h-[400px] bg-primary/5 rounded-full blur-3xl" />
        </div>

        <div className="relative max-w-3xl mx-auto">
          <h1 className="text-5xl sm:text-6xl font-bold tracking-tight mb-6 leading-[1.1]">
            Turn PDFs into{' '}
            <span className="text-primary">Excel</span>{' '}
            spreadsheets
            <br />
            <span className="text-muted-foreground text-4xl sm:text-5xl">in seconds</span>
          </h1>

          <p className="text-muted-foreground text-lg mb-10 max-w-xl mx-auto leading-relaxed">
            Upload any PDF, define the fields you need, and get a perfectly structured spreadsheet — powered by GPT-4.
          </p>

          <div className="flex flex-col sm:flex-row items-center gap-4 justify-center">
            <Button
              size="xl"
              onClick={() => googleLogin()}
              disabled={loading}
              className="gap-3 shadow-lg shadow-primary/20 min-w-[220px]"
            >
              {loading ? (
                <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-white rounded-full animate-spin" />
              ) : (
                <svg className="w-4 h-4" viewBox="0 0 24 24">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                </svg>
              )}
              Continue with Google
            </Button>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-16 px-6 border-t border-border/50">
        <div className="max-w-4xl mx-auto">
          <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-10">
            Everything you need
          </p>
          <div className="grid sm:grid-cols-3 gap-5">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="bg-card border border-border rounded-xl p-5 hover:border-primary/30 transition-colors"
              >
                <div className="w-9 h-9 bg-primary/10 rounded-lg flex items-center justify-center mb-4">
                  <f.icon size={17} className="text-primary" />
                </div>
                <h3 className="font-semibold text-sm mb-1.5">{f.title}</h3>
                <p className="text-muted-foreground text-xs leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

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
