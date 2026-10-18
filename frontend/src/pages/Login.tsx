import { useState } from 'react'
import type { FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ApiError } from '../lib/api'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const redirectTo = (location.state as { from?: string } | null)?.from ?? '/'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await login(email.trim(), password)
      navigate(redirectTo, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not log in.')
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-app-bg font-sans text-ink">
      <div className="w-full max-w-sm rounded-2xl border border-card-border bg-white p-8">
        <div className="mb-1 font-heading text-xl font-extrabold">CodeCanvas</div>
        <div className="mb-6 text-sm text-muted">Sign in to continue.</div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3.5">
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold text-slate-pill-text">Email</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              className="w-full rounded-md border border-input-border px-3 py-2 text-sm"
              required
              autoFocus
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold text-slate-pill-text">Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full rounded-md border border-input-border px-3 py-2 text-sm"
              required
            />
          </label>

          {error && <div className="text-sm text-red-text">{error}</div>}

          <button
            type="submit"
            disabled={!email.trim() || !password || submitting}
            className="mt-2 rounded-lg bg-accent py-2.5 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <div className="mt-6 rounded-lg bg-app-bg px-3.5 py-3 text-[11.5px] leading-relaxed text-faint">
          Demo accounts (password <code className="rounded bg-white px-1 py-0.5">codecanvas123</code> for all):
          <br />
          admin@codecanvas.demo · priya.nair@codecanvas.demo (Module Lead) · ankit.buffalo@gmail.com (Solution
          Architect)
        </div>
      </div>
    </div>
  )
}
