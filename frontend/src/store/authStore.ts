import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface User {
  id: string
  email: string
  name: string
  picture?: string
  balance: number
  subscription_tier: string
  subscription_status: string
  files_used_this_period: number
  current_period_end?: string | null
}

interface AuthState {
  user: User | null
  token: string | null
  setUser: (user: User, token: string) => void
  updateBalance: (balance: number) => void
  updateSubscription: (data: Partial<Pick<User, 'subscription_tier' | 'subscription_status' | 'files_used_this_period' | 'current_period_end'>>) => void
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
      updateSubscription: (data) =>
        set((state) => ({
          user: state.user ? { ...state.user, ...data } : null,
        })),
      logout: () => set({ user: null, token: null }),
    }),
    {
      name: 'gridpull-auth-v5',
    }
  )
)
