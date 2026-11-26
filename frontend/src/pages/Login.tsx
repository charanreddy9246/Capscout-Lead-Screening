import { useState, type FormEvent } from 'react'
import { ApiError } from '../api'
import { useAuth } from '../auth'
import { Logo } from '../components/Logo'
import { IconArrow } from '../components/icons'
import { MobileField } from '../components/widgets'

export default function Login() {
  const { login } = useAuth()
  const [code, setCode] = useState('')
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login(code.trim(), phone, password)
    } catch (err) {
      setError(err instanceof ApiError && typeof err.detail === 'string' ? err.detail : 'Could not sign in')
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="login" onSubmit={submit}>
      <div className="hdr">
        <Logo size="big" />
        <div style={{ fontSize: 24, fontWeight: 700, marginTop: 18 }}>Sign in</div>
      </div>
      <div className="scroll" style={{ paddingTop: 20 }}>
        {import.meta.env.VITE_DEMO === 'true' && (
          <div style={{ fontSize: 13, lineHeight: 1.4, color: "var(--muted)" }}>
            Demo version with sample data. Type any email, mobile number and password. An email starting with "admin" opens the Admin view, and one starting with "super" opens the Super Admin view.
          </div>
        )}
        <div>
          <label className="lbl" htmlFor="l-code">
            Email
          </label>
          <input
            className="fld"
            id="l-code"
            type="email"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            autoComplete="off"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            required
            autoFocus
          />
        </div>
        <MobileField id="l-phone" label="Phone number" value={phone} onChange={setPhone} />
        <div>
          <label className="lbl" htmlFor="l-pass">
            Password
          </label>
          <div className="box">
            <input
              id="l-pass"
              type={show ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              style={{ fontWeight: 500 }}
              required
            />
            <button
              type="button"
              onClick={() => setShow((s) => !s)}
              style={{ border: 'none', background: 'none', color: 'var(--navy)', fontWeight: 700, fontSize: 14 }}
              aria-label={show ? 'Hide password' : 'Show password'}
            >
              {show ? 'Hide' : 'Show'}
            </button>
          </div>
        </div>
        {error && (
          <div className="err" role="alert">
            {error}
          </div>
        )}
        <div style={{ fontSize: 13, color: 'var(--muted)', textAlign: 'center' }}>
          Forgot your password? Ask your admin to reset it.
        </div>
      </div>
      <div className="foot">
        <div className="inner">
          <button className="btn primary" style={{ width: '100%', height: 56, fontSize: 17 }} disabled={busy || !code || phone.length !== 10 || !password}>
            {busy ? 'Signing in…' : 'Sign in'} {!busy && <IconArrow />}
          </button>
        </div>
      </div>
    </form>
  )
}
