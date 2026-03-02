import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGoogleLogin } from '@react-oauth/google'
import { FileSpreadsheet, Zap, BarChart3, ArrowRight, Check } from 'lucide-react'
import api from '@/lib/api'
import { useAuthStore } from '@/store/authStore'
import toast from 'react-hot-toast'

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
    onError: () => {
      toast.error('Google login failed.')
      setLoading(false)
    },
  })

  if (user) {
    navigate('/dashboard')
    return null
  }

  return (
    <div className="min-h-screen bg-[#EFF6FF]">
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white/90 backdrop-blur-sm border-b border-blue-100">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
              <FileSpreadsheet className="w-4.5 h-4.5 text-white" size={18} />
            </div>
            <span className="font-semibold text-slate-900 text-lg tracking-tight">PDF to Excel</span>
          </div>

          {/* Dashboard button */}
          <button
            onClick={() => googleLogin()}
            disabled={loading}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 shadow-sm hover:shadow-md disabled:opacity-60"
          >
            {loading ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <>
                Dashboard
                <ArrowRight size={15} />
              </>
            )}
          </button>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="pt-32 pb-24 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-blue-100 border border-blue-200 text-blue-700 px-4 py-1.5 rounded-full text-sm font-medium mb-8">
            <Zap size={14} />
            AI-Powered PDF Extraction
          </div>

          <h1 className="text-5xl md:text-6xl font-bold text-slate-900 leading-tight mb-6">
            Turn PDFs into
            <span className="text-blue-600"> Excel spreadsheets</span>
            <br />in seconds
          </h1>

          <p className="text-xl text-slate-500 mb-10 max-w-2xl mx-auto leading-relaxed">
            Upload any PDF documents, define your extraction fields, and get a perfectly structured
            Excel or CSV file — powered by AI.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <button
              onClick={() => googleLogin()}
              disabled={loading}
              className="flex items-center justify-center gap-3 bg-blue-600 hover:bg-blue-700 text-white px-8 py-4 rounded-xl text-base font-semibold transition-all duration-200 shadow-lg hover:shadow-xl disabled:opacity-60"
            >
              {loading ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  <svg className="w-5 h-5" viewBox="0 0 24 24">
                    <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                    <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                    <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                    <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                  </svg>
                  Continue with Google
                </>
              )}
            </button>
          </div>

          <p className="text-sm text-slate-400 mt-4">No credit card required to start</p>
        </div>
      </section>

      {/* Features */}
      <section className="py-20 px-6 bg-white">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-slate-900 mb-4">Everything you need</h2>
            <p className="text-slate-500 text-lg">Powerful extraction, simple workflow</p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                icon: FileSpreadsheet,
                title: 'Bulk PDF Upload',
                desc: 'Upload multiple PDFs at once. Drag & drop or click to select any number of files.',
                color: 'bg-blue-50 text-blue-600',
              },
              {
                icon: Zap,
                title: 'AI-Powered Extraction',
                desc: 'Define custom fields and our AI extracts exactly what you need from every document.',
                color: 'bg-amber-50 text-amber-600',
              },
              {
                icon: BarChart3,
                title: 'Excel & CSV Export',
                desc: 'Download your data as XLSX or CSV instantly. Clean, structured, ready to use.',
                color: 'bg-emerald-50 text-emerald-600',
              },
            ].map((feature) => (
              <div key={feature.title} className="bg-[#EFF6FF] rounded-2xl p-8 border border-blue-100 shadow-sm hover:shadow-md transition-shadow">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center mb-5 ${feature.color}`}>
                  <feature.icon size={24} />
                </div>
                <h3 className="font-semibold text-slate-900 text-lg mb-2">{feature.title}</h3>
                <p className="text-slate-500 leading-relaxed">{feature.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section className="py-20 px-6 bg-[#EFF6FF]">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl font-bold text-slate-900 mb-4">Simple credit-based pricing</h2>
          <p className="text-slate-500 text-lg mb-12">Pay only for what you use</p>

          <div className="grid md:grid-cols-3 gap-6">
            {[
              { credits: 10, price: '$5', desc: 'Perfect to get started', popular: false },
              { credits: 50, price: '$20', desc: 'Best for regular use', popular: true },
              { credits: 200, price: '$60', desc: 'For power users', popular: false },
            ].map((plan) => (
              <div
                key={plan.credits}
                className={`rounded-2xl p-8 border ${plan.popular ? 'border-blue-300 bg-blue-50 ring-2 ring-blue-200' : 'border-blue-100 bg-white'}`}
              >
                {plan.popular && (
                  <div className="text-xs font-semibold text-blue-600 bg-blue-100 rounded-full px-3 py-1 inline-block mb-4">
                    Most Popular
                  </div>
                )}
                <div className="text-3xl font-bold text-slate-900 mb-1">{plan.price}</div>
                <div className="text-lg font-medium text-slate-700 mb-2">{plan.credits} credits</div>
                <p className="text-slate-500 text-sm mb-6">{plan.desc}</p>
                <div className="space-y-2 text-sm text-slate-600">
                  <div className="flex items-center gap-2"><Check size={14} className="text-emerald-500" /> 1 credit per PDF page</div>
                  <div className="flex items-center gap-2"><Check size={14} className="text-emerald-500" /> All export formats</div>
                  <div className="flex items-center gap-2"><Check size={14} className="text-emerald-500" /> Custom field extraction</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-blue-100 bg-white py-8 px-6">
        <div className="max-w-7xl mx-auto flex items-center justify-between text-sm text-slate-400">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 bg-blue-600 rounded flex items-center justify-center">
              <FileSpreadsheet size={11} className="text-white" />
            </div>
            GridPull
          </div>
          <div>© 2026 GridPull. All rights reserved.</div>
        </div>
      </footer>
    </div>
  )
}
