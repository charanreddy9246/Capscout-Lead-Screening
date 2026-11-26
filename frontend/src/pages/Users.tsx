// User Management. Admin: creates and manages SMs. Super Admin: creates and manages Admins (and SMs).
// There is no sign-up: a new person gets a one-time set-password link that the admin passes on.

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { api, ApiError, post, type Invite, type Role, type UserRow } from '../api'
import { useAuth } from '../auth'
import AdminShell from '../components/AdminShell'
import { MobileField } from '../components/widgets'
import { ROLE } from './Home'

type Created = { name: string; invite: Invite }

export default function Users() {
  const { staff } = useAuth()
  const isSuper = staff?.role === 'SUPER_ADMIN'
  const [rows, setRows] = useState<UserRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [link, setLink] = useState<Created | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(() => {
    api<{ items: UserRow[] }>('/users')
      .then((d) => setRows(d.items))
      .catch(() => setError('Could not load the users.'))
  }, [])
  useEffect(load, [load])

  async function act(id: string, run: () => Promise<unknown>) {
    setBusy(id)
    setError(null)
    try {
      await run()
      load()
    } catch (e) {
      setError(e instanceof ApiError && typeof e.detail === 'string' ? e.detail : 'That did not work. Try again.')
    } finally {
      setBusy(null)
    }
  }

  const patch = (id: string, body: object) => act(id, () => api(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) }))
  const reissue = (u: UserRow) =>
    act(u.id, async () => setLink({ name: u.full_name, invite: await post<Invite>(`/users/${u.id}/invite`) }))

  const groups: { title: string; role: Role }[] = isSuper
    ? [
        { title: 'Admins', role: 'ADMIN' },
        { title: 'Sales managers', role: 'SM' },
      ]
    : [{ title: 'Sales managers', role: 'SM' }]

  return (
    <AdminShell>
      <div className="page-fixed">
        <div className="page-head">
          <div>
            <div className="page-title">Users</div>
            <div className="page-sub">Create accounts and switch them off. There is no sign-up.</div>
          </div>
          <button type="button" className="gps-refresh" onClick={() => setAdding(true)}>
            + Add
          </button>
        </div>
      </div>

      <div className="scroll">
        {error && (
          <div className="err" role="alert">
            {error}
          </div>
        )}
        {!rows && !error && <div className="empty">Loading…</div>}
        {rows &&
          groups.map((g) => {
            const list = rows.filter((r) => r.role === g.role)
            return (
              <section key={g.role} className="list-section" aria-label={g.title}>
                <div className="list-title">
                  {g.title} <span className="list-count">{list.length}</span>
                </div>
                {list.length === 0 && <div className="muted" style={{ fontSize: 14 }}>None yet.</div>}
                <div className="lead-grid">
                  {list.map((u) => (
                    <div key={u.id} className="lead" style={{ cursor: 'default', opacity: u.is_active ? 1 : 0.6 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                        <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--navy)', minWidth: 0 }}>{u.full_name}</div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                          <span className={`tag ${u.is_active ? 'good' : 'bad'}`}>{u.is_active ? 'Active' : 'Switched off'}</span>
                          {u.manageable && (
                            <ActionMenu
                              label={`Actions for ${u.full_name}`}
                              disabled={busy === u.id}
                              items={[
                                { label: 'Set-password link', onClick: () => reissue(u) },
                                { label: u.is_active ? 'Switch off' : 'Switch on', onClick: () => patch(u.id, { is_active: !u.is_active }) },
                                ...(isSuper
                                  ? [
                                      {
                                        label: u.role === 'SM' ? 'Make Admin' : 'Make SM',
                                        onClick: () => confirm(`Make ${u.full_name} ${u.role === 'SM' ? 'an Admin' : 'a Sales Manager'}?`) && patch(u.id, { role: u.role === 'SM' ? 'ADMIN' : 'SM' }),
                                      },
                                    ]
                                  : []),
                              ]}
                            />
                          )}
                        </div>
                      </div>
                      <div className="muted" style={{ fontSize: 13 }}>
                        {u.email} · +91 {u.phone ?? '—'}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )
          })}
      </div>

      {adding && (
        <AddUser
          canMakeAdmin={isSuper}
          onClose={() => setAdding(false)}
          onCreated={(c) => {
            setAdding(false)
            setLink(c)
            load()
          }}
        />
      )}
      {link && <LinkSheet created={link} onClose={() => setLink(null)} />}
    </AdminShell>
  )
}

function AddUser({ canMakeAdmin, onClose, onCreated }: { canMakeAdmin: boolean; onClose: () => void; onCreated: (c: Created) => void }) {
  const [role, setRole] = useState<Role>('SM')
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const u = await post<UserRow & { invite: Invite }>('/users', { full_name: name.trim(), phone, email: email.trim(), role })
      onCreated({ name: u.full_name, invite: u.invite })
    } catch (err) {
      setError(err instanceof ApiError && typeof err.detail === 'string' ? err.detail : 'Could not create the account.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="sheet-bg" role="dialog" aria-modal="true" aria-labelledby="add-user">
      <form className="sheet" onSubmit={submit}>
        <div className="sheet-title" id="add-user">
          Add {role === 'ADMIN' ? 'an Admin' : 'a sales manager'}
        </div>
        {canMakeAdmin && (
          <div className="opts" style={{ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }} role="radiogroup" aria-label="Role">
            {(['SM', 'ADMIN'] as const).map((r) => (
              <button key={r} type="button" className={`chip${role === r ? ' on' : ''}`} aria-pressed={role === r} onClick={() => setRole(r)}>
                {ROLE[r]}
              </button>
            ))}
          </div>
        )}
        <div>
          <label className="lbl" htmlFor="u-name">
            Full name
          </label>
          <input autoComplete="off" id="u-name" className="fld" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
        </div>
        <MobileField id="u-phone" label="Mobile" value={phone} onChange={setPhone} />
        <div>
          <label className="lbl" htmlFor="u-email">
            Email
          </label>
          <input autoComplete="off" id="u-email" className="fld" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
            We email a link to this address so they can set their password. They sign in with it.
          </div>
        </div>
        {error && (
          <div className="err" role="alert">
            {error}
          </div>
        )}
        <button className="btn primary" disabled={busy || !name.trim() || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim()) || phone.length !== 10}>
          {busy ? 'Creating…' : 'Create account and email the link'}
        </button>
        <button type="button" className="btn ghost" style={{ border: 'none' }} onClick={onClose}>
          Cancel
        </button>
      </form>
    </div>
  )
}

function LinkSheet({ created, onClose }: { created: Created; onClose: () => void }) {
  const url = `${window.location.origin}${created.invite.path}`
  const [copied, setCopied] = useState(false)
  const mail = created.invite.email
  const sent = !!mail?.sent
  const copy = (
    <button className="btn primary" onClick={() => navigator.clipboard?.writeText(url).then(() => setCopied(true), () => setCopied(false))}>
      {copied ? 'Copied' : 'Copy link'}
    </button>
  )
  const linkBox = (
    <div className="fld" style={{ height: 'auto', padding: '10px 14px', fontSize: 13, wordBreak: 'break-all', userSelect: 'all' }}>
      {url}
    </div>
  )
  return (
    <div className="sheet-bg" role="dialog" aria-modal="true" aria-labelledby="link-title">
      <div className="sheet">
        <div className="sheet-title" id="link-title">
          {sent ? `Email sent to ${mail?.to}` : `Send this link to ${created.name}`}
        </div>
        {sent ? (
          <>
            <div className="muted" style={{ fontSize: 14 }}>
              {created.name} opens the email, sets a password and signs in. The link works once and stops after {created.invite.valid_hours} hours.
            </div>
            <details>
              <summary className="muted" style={{ fontSize: 13, cursor: 'pointer' }}>
                Show the link instead
              </summary>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 8 }}>
                {linkBox}
                {copy}
              </div>
            </details>
          </>
        ) : (
          <>
            {mail?.error && (
              <div className="err" role="alert">
                The email was not sent: {mail.error} Share the link yourself instead.
              </div>
            )}
            <div className="muted" style={{ fontSize: 14 }}>
              They open it, choose a password and sign in. The link works once and stops after {created.invite.valid_hours} hours. Share it privately.
            </div>
            {linkBox}
            {copy}
          </>
        )}
        <button className="btn ghost" style={{ border: 'none' }} onClick={onClose}>
          Done
        </button>
      </div>
    </div>
  )
}

// The three dots at the end of a person's name: tap for the things you can do with that account.
function ActionMenu({ label, items, disabled }: { label: string; items: { label: string; onClick: () => void }[]; disabled?: boolean }) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const away = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false)
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', away)
      document.removeEventListener('keydown', esc)
    }
  }, [open])
  return (
    <div ref={box} style={{ position: 'relative' }}>
      <button
        type="button"
        className="icon-btn"
        style={{ width: 36, height: 36, color: 'var(--muted)' }}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <circle cx="12" cy="5" r="2" />
          <circle cx="12" cy="12" r="2" />
          <circle cx="12" cy="19" r="2" />
        </svg>
      </button>
      {open && (
        <div
          role="menu"
          style={{ position: 'absolute', right: 0, top: 38, zIndex: 20, minWidth: 180, background: '#fff', border: '1px solid var(--line)', borderRadius: 12, boxShadow: '0 8px 24px rgba(18,38,58,0.16)', padding: 6, display: 'flex', flexDirection: 'column' }}
        >
          {items.map((it) => (
            <button
              key={it.label}
              type="button"
              role="menuitem"
              style={{ textAlign: 'left', padding: '12px 12px', borderRadius: 8, fontSize: 15, fontWeight: 600, color: 'var(--navy)', background: 'none', border: 0, cursor: 'pointer' }}
              onClick={() => {
                setOpen(false)
                it.onClick()
              }}
            >
              {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
