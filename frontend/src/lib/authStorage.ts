// Tiny wrapper around localStorage for the JWT. Deliberately not using
// cookies/httpOnly storage -- this is a dev/demo single-tenant tool, and a
// localStorage token keeps the frontend fully static-hostable with no
// server-side session. A real production deploy should reconsider this
// (XSS exposes the token) in favor of an httpOnly cookie.
const KEY = 'codecanvas_token'

export function getToken(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function setToken(token: string) {
  try {
    localStorage.setItem(KEY, token)
  } catch {
    // ignore -- storage unavailable (private browsing, etc.)
  }
}

export function clearToken() {
  try {
    localStorage.removeItem(KEY)
  } catch {
    // ignore
  }
}
