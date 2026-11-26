// One follow-up: who, why, when. The SM can complete it (with an outcome and, if wanted, the next one) or move it.
// Admins and the Super Admin see the same card without the buttons.

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, post, type FollowUp } from '../api'
import { displayName } from '../format'

// <input type="datetime-local"> works in local time: turn it into a moment with a timezone, and back.
export const toInput = (iso: string) => {
  const d = new Date(iso)
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 16)
}
export const fromInput = (v: string) => new Date(v).toISOString()
export const nextMorning = () => {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  d.setHours(10, 0, 0, 0)
  return toInput(d.toISOString())
}

export const whenText = (iso: string) =>
  new Date(iso).toLocaleString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })

export default function FollowUpCard({
  f,
  canAct,
  showCustomer = true,
  onChanged,
}: {
  f: FollowUp
  canAct: boolean
  showCustomer?: boolean
  onChanged: () => void
}) {
  const [mode, setMode] = useState<'view' | 'done' | 'move'>('view')
  const [outcome, setOutcome] = useState('')
  const [then, setThen] = useState('')
  const [when, setWhen] = useState(toInput(f.due_at))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const c = f.customer
  const name = displayName({ business_name: c.business_name, promoter: c.promoter, lead_ref: 'Customer' })

  async function run(job: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await job()
      setMode('view')
      onChanged()
    } catch (e) {
      setError(e instanceof ApiError && typeof e.detail === 'string' ? e.detail : 'That did not work. Try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card" style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0 }}>
          {showCustomer ? (
            <Link to={`/customers/${c.id}`} style={{ fontSize: 16, fontWeight: 700, color: 'var(--navy)', textDecoration: 'none' }}>
              {name}
            </Link>
          ) : (
            <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--navy)' }}>{f.purpose ?? 'Follow-up'}</div>
          )}
          {showCustomer && (
            <div className="muted" style={{ fontSize: 13 }}>
              {[c.converted ? (c.loan_stage ?? 'Lead') : 'Meeting stage', f.purpose].filter(Boolean).join(' · ')}
            </div>
          )}
          {c.owner_name && !canAct && (
            <div className="muted" style={{ fontSize: 12 }}>
              Sales manager: {c.owner_name}
            </div>
          )}
        </div>
        <div className="mono" style={{ fontSize: 13, fontWeight: 700, color: f.when === 'overdue' ? 'var(--warn)' : 'var(--navy)', textAlign: 'right' }}>
          {f.status === 'DONE' && f.completed_at ? `Done ${whenText(f.completed_at)}` : whenText(f.due_at)}
        </div>
      </div>
      {f.outcome && (
        <div style={{ fontSize: 13 }}>
          <b>Outcome:</b> {f.outcome}
        </div>
      )}

      {canAct && f.status === 'PENDING' && mode === 'view' && (
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" className="gps-refresh" onClick={() => setMode('done')}>
            Done
          </button>
          <button type="button" className="gps-refresh" onClick={() => setMode('move')}>
            Reschedule
          </button>
        </div>
      )}

      {mode === 'done' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <label className="lbl" htmlFor={`o-${f.id}`}>
            Outcome
          </label>
          <textarea
            id={`o-${f.id}`}
            className="fld"
            style={{ height: 72, resize: 'none', padding: '10px 12px' }}
            placeholder="What happened? e.g. Will send bank statements on Friday"
            value={outcome}
            onChange={(e) => setOutcome(e.target.value)}
          />
          <label className="lbl" htmlFor={`n-${f.id}`}>
            Next follow-up (optional)
          </label>
          <input id={`n-${f.id}`} className="fld" type="datetime-local" value={then} onChange={(e) => setThen(e.target.value)} />
          {!then && (
            <button type="button" className="gps-refresh" style={{ alignSelf: 'flex-start' }} onClick={() => setThen(nextMorning())}>
              Tomorrow 10:00
            </button>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="button"
              className="gps-refresh"
              disabled={busy}
              onClick={() => run(() => post(`/follow-ups/${f.id}/complete`, { outcome, next: then ? { due_at: fromInput(then) } : undefined }))}
            >
              Save
            </button>
            <button type="button" className="gps-refresh" onClick={() => setMode('view')}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {mode === 'move' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <input aria-label="New date and time" className="fld" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="button"
              className="gps-refresh"
              disabled={busy || !when}
              onClick={() => run(() => api(`/follow-ups/${f.id}`, { method: 'PATCH', body: JSON.stringify({ due_at: fromInput(when) }) }))}
            >
              Save
            </button>
            <button type="button" className="gps-refresh" onClick={() => setMode('view')}>
              Cancel
            </button>
          </div>
        </div>
      )}
      {error && <div className="err">{error}</div>}
    </div>
  )
}
