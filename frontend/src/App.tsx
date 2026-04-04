import { Component, ReactNode, useEffect, lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { trackPageView } from '@/lib/analytics'
import LandingPage from '@/pages/LandingPage'
import InsurancePage from '@/pages/InsurancePage'
import AccountingFinancePage from '@/pages/AccountingFinancePage'
import OtherUseCasesPage from '@/pages/OtherUseCasesPage'
import PrivacyPage from '@/pages/PrivacyPage'
import TermsPage from '@/pages/TermsPage'
import DashboardPage from '@/pages/DashboardPage'
import SettingsPage from '@/pages/SettingsPage'
import PipelinesPage from '@/pages/PipelinesPage'
import FormFillingPage from '@/pages/FormFillingPage'
import MobileUploadPage from '@/pages/MobileUploadPage'
import { useAuthStore } from '@/store/authStore'
import DashboardLayout from '@/components/layout/DashboardLayout'
import AutoLoginPage from '@/pages/AutoLoginPage'

const ResourcesHub = lazy(() => import('@/pages/resources/ResourcesHub'))
const ResourcePage = lazy(() => import('@/pages/resources/ResourcePage'))

class ErrorBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null }
  static getDerivedStateFromError(e: Error) { return { error: e.message } }
  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen flex items-center justify-center p-8 text-center">
          <div>
            <p className="text-sm font-medium text-foreground mb-2">Something went wrong</p>
            <p className="text-xs text-muted-foreground font-mono bg-secondary p-3 rounded-lg max-w-xl">{this.state.error}</p>
            <button onClick={() => window.location.reload()} className="mt-4 text-xs text-primary underline">Reload</button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user } = useAuthStore()
  if (!user) return <Navigate to="/" replace />
  return <>{children}</>
}

function PageViewTracker() {
  const location = useLocation()
  useEffect(() => {
    trackPageView(location.pathname, document.title)
  }, [location.pathname])
  return null
}

function ResourcesLoader() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <PageViewTracker />
      <ErrorBoundary>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <DashboardLayout>
                <DashboardPage />
              </DashboardLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/settings"
          element={
            <ProtectedRoute>
              <DashboardLayout>
                <SettingsPage />
              </DashboardLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/pipelines"
          element={
            <ProtectedRoute>
              <DashboardLayout>
                <PipelinesPage />
              </DashboardLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/form-filling"
          element={
            <ProtectedRoute>
              <DashboardLayout>
                <FormFillingPage />
              </DashboardLayout>
            </ProtectedRoute>
          }
        />
        <Route path="/auto-login" element={<AutoLoginPage />} />
        <Route path="/upload/:token" element={<MobileUploadPage />} />
        <Route path="/use-cases/insurance" element={<InsurancePage />} />
        <Route path="/use-cases/accounting-finance" element={<AccountingFinancePage />} />
        <Route path="/use-cases/other" element={<OtherUseCasesPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/resources" element={<Suspense fallback={<ResourcesLoader />}><ResourcesHub /></Suspense>} />
        <Route path="/resources/:slug" element={<Suspense fallback={<ResourcesLoader />}><ResourcePage /></Suspense>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </ErrorBoundary>
    </BrowserRouter>
  )
}
