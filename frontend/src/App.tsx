import { Component, ReactNode, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { trackPageView } from '@/lib/analytics'
import LandingPage from '@/pages/LandingPage'
import PrivacyPage from '@/pages/PrivacyPage'
import TermsPage from '@/pages/TermsPage'
import DashboardPage from '@/pages/DashboardPage'
import SettingsPage from '@/pages/SettingsPage'
import PipelinesPage from '@/pages/PipelinesPage'
import { useAuthStore } from '@/store/authStore'
import DashboardLayout from '@/components/layout/DashboardLayout'

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
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </ErrorBoundary>
    </BrowserRouter>
  )
}
