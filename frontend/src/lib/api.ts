import axios from 'axios'
import { useAuthStore } from '@/store/authStore'

// No Content-Type default — axios sets it automatically per request:
//   plain object → application/json
//   FormData     → multipart/form-data; boundary=<generated>
const api = axios.create({
  baseURL: '/api',
})

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const url: string = error.config?.url ?? ''
    // Never auto-logout on auth endpoint failures (login errors are handled inline)
    if (error.response?.status === 401 && !url.startsWith('/auth/')) {
      useAuthStore.getState().logout()
      window.location.href = '/'
    }
    return Promise.reject(error)
  }
)

export default api
