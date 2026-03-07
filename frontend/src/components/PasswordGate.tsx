import { useState, type ReactNode, type FormEvent } from 'react'
import { Lock, FileSpreadsheet } from 'lucide-react'

const STORAGE_KEY = 'gridpull-site-access'
const SITE_PASSWORD = 'marti'

export default function PasswordGate({ children }: { children: ReactNode }) {
  const [unlocked, setUnlocked] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'granted'
    } catch {
      return false
    }
  })
  const [password, setPassword] = useState('')
  const [error, setError] = useState(false)

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (password === SITE_PASSWORD) {
      localStorage.setItem(STORAGE_KEY, 'granted')
      setUnlocked(true)
      setError(false)
    } else {
      setError(true)
    }
  }

  if (unlocked) return <>{children}</>

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="w-12 h-12 bg-primary rounded-xl flex items-center justify-center mx-auto mb-4">
            <FileSpreadsheet size={22} className="text-white" />
          </div>
          <h1 className="text-xl font-semibold text-foreground mb-1">PDF to Excel</h1>
          <p className="text-sm text-muted-foreground">This site is currently in preview. Enter the password to continue.</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="relative">
            <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="password"
              value={password}
              onChange={(e) => { setPassword(e.target.value); setError(false) }}
              placeholder="Enter password"
              autoFocus
              className={`w-full pl-9 pr-4 py-2.5 text-sm rounded-xl border bg-card outline-none transition-colors ${
                error
                  ? 'border-red-300 focus:border-red-400'
                  : 'border-border focus:border-primary'
              }`}
            />
          </div>
          {error && (
            <p className="text-xs text-red-500">Incorrect password. Please try again.</p>
          )}
          <button
            type="submit"
            className="w-full py-2.5 text-sm font-medium rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            Continue
          </button>
        </form>
      </div>
    </div>
  )
}
