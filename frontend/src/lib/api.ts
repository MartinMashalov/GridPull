import axios from 'axios'
import { useAuthStore } from '@/store/authStore'

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
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
    // Only auto-logout on 401 from auth/user endpoints, not extraction or payments
    if (error.response?.status === 401) {
      const url: string = error.config?.url ?? ''
      const isAuthEndpoint = url.includes('/auth/') || url.includes('/users/me')
      if (isAuthEndpoint) {
        useAuthStore.getState().logout()
        window.location.href = '/'
      }
    }
    return Promise.reject(error)
  }
)

export default api
