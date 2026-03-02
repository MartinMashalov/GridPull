import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface User {
  id: string
  email: string
  name: string
  picture?: string
  credits: number
}

interface AuthState {
  user: User | null
  token: string | null
  setUser: (user: User, token: string) => void
  updateCredits: (credits: number) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      setUser: (user, token) => set({ user, token }),
      updateCredits: (credits) =>
        set((state) => ({
          user: state.user ? { ...state.user, credits } : null,
        })),
      logout: () => set({ user: null, token: null }),
    }),
    {
      name: 'gridpull-auth',
    }
  )
)
