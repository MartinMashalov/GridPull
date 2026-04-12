import { useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import api from '@/lib/api'
import { useAuthStore } from '@/store/authStore'

/**
 * Dev bypass login page.
 * Navigate to /auto-login?t=<DEV_LOGIN_SECRET> to skip OAuth and log straight in.
 * The endpoint is disabled server-side unless DEV_LOGIN_SECRET is set in .env.
 */
export default function AutoLoginPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { setUser } = useAuthStore()
  const attempted = useRef(false)

  useEffect(() => {
    if (attempted.current) return
    attempted.current = true

    const secret = params.get('t') || ''
    if (!secret) {
      navigate('/', { replace: true })
      return
    }

    api.post('/auth/dev-login', { secret })
      .then((res) => {
        setUser(res.data.user, res.data.access_token)
        navigate('/form-filling', { replace: true })
      })
      .catch(() => {
        navigate('/', { replace: true })
      })
  }, [params, navigate, setUser])

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  )
}
