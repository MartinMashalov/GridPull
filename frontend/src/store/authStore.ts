import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface User {
  id: string
  email: string
  name: string
  picture?: string
  balance: number
  auto_renewal_enabled?: boolean
  auto_renewal_threshold?: number
  auto_renewal_refill?: number
}

interface AuthState {
  user: User | null
  token: string | null
  setUser: (user: User, token: string) => void
  updateBalance: (balance: number) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      setUser: (user, token) => set({ user, token }),
      updateBalance: (balance) =>
        set((state) => ({
          user: state.user ? { ...state.user, balance } : null,
        })),
      logout: () => set({ user: null, token: null }),
    }),
    {
      name: 'gridpull-auth-v4',
    }
  )
)
