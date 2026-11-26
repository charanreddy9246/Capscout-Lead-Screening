// Opened from the one-time link an admin sends. Works whether or not anyone is signed in.

import { useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError, post } from '../api'
import { Logo } from '../components/Logo'
import { IconArrow } from '../components/icons'

export default function SetPassword() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const token = params.get('token') ?? ''
  const [password, setPassword] = useState('')
  const [again, setAgain] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<string | null>(null)

  const short = password.length > 0 && password.length < 8
  const mismatch = again.length > 0 && again !== password

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const r = await post<{ email: string }>('/auth/set-password', { token, password })
      setDone(r.email)
    } catch (err) {
      setError(err instanceof ApiError && typeof err.detail === 'string' ? err.detail : 'Could not set the password. Try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="login" onSubmit={submit}>
      <div className="hdr" style={{ padding: '56px 22px 20px' }}>
        <Logo size="big" />
        <div style={{ fontSize: 24, fontWeight: 700, marginTop: 18 }}>{done ? 'Password set' : 'Choose your password'}</div>
      </div>
      <div className="scroll" style={{ paddingTop: 20 }}>
        {done ? (
          <div className="ok-banner">
            Your password is set. Sign in with <b>{done}</b>, your mobile number and this password.
          </div>
        ) : (
          <>
            {!token && <div className="err">This link is incomplete. Ask your admin for a new one.</div>}
            <div>
              <label className="lbl" htmlFor="p-new">
                New password
              </label>
              <div className="box">
                <input
                  autoComplete="new-password"
                  id="p-new"
                  type={show ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  style={{ fontWeight: 500 }}
                  required
                  autoFocus
                />
                <button type="button" onClick={() => setShow((s) => !s)} style={{ border: 'none', background: 'none', color: 'var(--navy)', fontWeight: 700, fontSize: 14 }}>
                  {show ? 'Hide' : 'Show'}
                </button>
              </div>
              <div className="muted" style={{ fontSize: 12, marginTop: 6, color: short ? 'var(--warn)' : undefined }}>
                At least 8 characters.
              </div>
            </div>
            <div>
              <label className="lbl" htmlFor="p-again">
                Type it again
              </label>
              <div className="box">
                <input autoComplete="new-password" id="p-again" type={show ? 'text' : 'password'} value={again} onChange={(e) => setAgain(e.target.value)} style={{ fontWeight: 500 }} required />
              </div>
              {mismatch && <div style={{ fontSize: 12, marginTop: 6, color: 'var(--warn)' }}>The two passwords are different.</div>}
            </div>
            {error && (
              <div className="err" role="alert">
                {error}
              </div>
            )}
          </>
        )}
      </div>
      <div className="foot">
        <div className="inner">
          {done ? (
            <button type="button" className="btn primary" style={{ width: '100%', height: 56, fontSize: 17 }} onClick={() => navigate('/', { replace: true })}>
              Go to sign in <IconArrow />
            </button>
          ) : (
            <button className="btn primary" style={{ width: '100%', height: 56, fontSize: 17 }} disabled={busy || !token || password.length < 8 || password !== again}>
              {busy ? 'Saving…' : 'Set password'} {!busy && <IconArrow />}
            </button>
          )}
        </div>
      </div>
    </form>
  )
}
