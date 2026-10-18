import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { getMe, login as apiLogin, setUnauthorizedHandler } from '../lib/api'
import { clearToken, getToken, setToken } from '../lib/authStorage'
import type { User } from '../lib/types'

interface AuthContextValue {
  user: User | null
  status: 'checking' | 'authenticated' | 'anonymous'
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState<AuthContextValue['status']>('checking')

  useEffect(() => {
    setUnauthorizedHandler(() => {
      clearToken()
      setUser(null)
      setStatus('anonymous')
    })
    return () => setUnauthorizedHandler(null)
  }, [])

  // On first load, validate any stored token against the server rather
  // than trusting it blindly -- it may have expired, or the server may
  // have restarted with a fresh in-memory JWT secret (dev-only situation,
  // but worth handling gracefully instead of showing a broken app).
  useEffect(() => {
    const token = getToken()
    if (!token) {
      setStatus('anonymous')
      return
    }
    getMe()
      .then((me) => {
        setUser(me)
        setStatus('authenticated')
      })
      .catch(() => {
        clearToken()
        setStatus('anonymous')
      })
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      status,
      login: async (email, password) => {
        const res = await apiLogin(email, password)
        setToken(res.access_token)
        setUser(res.user)
        setStatus('authenticated')
      },
      logout: () => {
        clearToken()
        setUser(null)
        setStatus('anonymous')
      },
    }),
    [user, status],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
