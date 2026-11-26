import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, ApiError, type CustomerCard, type CustomerList, type DealList, type FollowUpList, type HomeSummary } from '../api'
import { useAuth } from '../auth'
import DealCard from '../components/DealCard'
import FollowUpCard from '../components/FollowUpCard'
import { Logo } from '../components/Logo'
import { IconCal, IconCloud, IconPlus, IconPower, IconSearch } from '../components/icons'
import { displayName, formatINR, isoDate, nextActionWhen } from '../format'

export const ROLE: Record<string, string> = { SM: 'Sales Manager', ADMIN: 'Admin', SUPER_ADMIN: 'Super Admin' }
const GRADE_COLORS: Record<string, [string, string]> = {
  A: ['#1F6F4A', '#fff'],
  B: ['#12263A', '#fff'],
  C: ['#E7ECF1', '#12263A'],
  D: ['#9F1D1D', '#fff'],
}

type Tab = 'not_converted' | 'converted' | 'deals'

// The two tiles: each opens a list of prospects AND leads, in two separate sections.
const VIEWS = {
  followups: 'Follow-ups today',
  overdue: 'Overdue',
} as const
type View = keyof typeof VIEWS

// Under Meetings: who the meeting was with. Banker and Connector meetings have their own forms (coming).
const KINDS = [
  { key: 'customer', label: 'Customer' },
  { key: 'banker', label: 'Banker' },
  { key: 'connector', label: 'Connector' },
]

export default function Home() {
  const { staff, logout } = useAuth()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const tab: Tab = params.get('tab') === 'converted' ? 'converted' : params.get('tab') === 'deals' ? 'deals' : 'not_converted'
  const view: View | null = (Object.keys(VIEWS) as View[]).find((v) => v === params.get('view')) ?? null
  const isAdmin = staff?.role !== 'SM' // an Admin (and the Super Admin) can look at everyone's customers
  // An Admin or Super Admin does field work too, so they choose: their OWN customers, or everyone's (read-only).
  const [scope, setScopeState] = useState<'mine' | 'all'>(() => {
    try {
      return localStorage.getItem('capscout-scope') === 'all' ? 'all' : 'mine'
    } catch {
      return 'mine'
    }
  })
  const setScope = (s: 'mine' | 'all') => {
    setScopeState(s)
    try {
      localStorage.setItem('capscout-scope', s)
    } catch {
      // private window: the choice is simply not remembered
    }
  }
  const viewingMine = !isAdmin || scope === 'mine' // these are my own customers: I can work on them
  const mineQ = isAdmin && scope === 'mine' ? 'mine=true' : ''
  const today = isoDate(new Date())
  const kind = tab === 'converted' ? 'customer' : (KINDS.find((k) => k.key === params.get('kind'))?.key ?? 'customer')
  const [query, setQuery] = useState('')
  const [list, setList] = useState<CustomerList | null>(null)
  const [summary, setSummary] = useState<HomeSummary | null>(null)
  const [tick, setTick] = useState(0) // bumped to re-check while Zoho is still working
  const [fus, setFus] = useState<FollowUpList | null>(null)
  const loadFus = useCallback(() => {
    api<FollowUpList>(`/follow-ups?status=pending${mineQ ? `&${mineQ}` : ''}`).then(setFus).catch(() => undefined)
  }, [mineQ])
  useEffect(loadFus, [loadFus, tick])

  useEffect(() => {
    api<HomeSummary>(`/customers/-/summary?today=${today}${mineQ ? `&${mineQ}` : ''}`).then(setSummary).catch(() => undefined)
  }, [tick, mineQ])

  useEffect(() => {
    let cancelled = false
    if (view || tab === 'deals') return // the tiles show follow-ups, and Deals loads from Zoho (below)
    if (!view && kind !== 'customer') {
      setList({ total: 0, items: [] }) // no banker or connector meetings are stored yet
      return
    }
    const t = setTimeout(() => {
      const q = new URLSearchParams(view ? { view, today, limit: '200' } : { tab, limit: '200' })
      if (query.trim()) q.set('q', query.trim())
      if (mineQ) q.set('mine', 'true')
      api<CustomerList>(`/customers?${q}`)
        .then((d) => !cancelled && setList(d))
        .catch(() => undefined)
    }, 200)
    return () => {
      cancelled = true
      clearTimeout(t)
    }
  }, [tab, kind, view, today, query, tick, mineQ])

  // While a lead is "Converting…" or a meeting is still going to Zoho, re-check every few seconds.
  const busy =
    (list?.items.some((c) => c.conversion_status === 'CONVERTING') ?? false) || (summary?.sync_pending ?? 0) > 0
  useEffect(() => {
    if (!busy) return
    const t = setInterval(() => setTick((n) => n + 1), 4000)
    return () => clearInterval(t)
  }, [busy])

  const items = list?.items ?? []

  const syncPill =
    summary && summary.sync_failed > 0
      ? { cls: 'failed', text: `${summary.sync_failed} failed` }
      : summary && summary.sync_pending > 0
        ? { cls: 'pending', text: `${summary.sync_pending} pending` }
        : { cls: '', text: 'Synced' }

  // A tile is a button: tap it to see those customers; tap it again to go back to the tabs.
  const tile = (key: View, n: number | undefined, hi = false) => (
    <button
      type="button"
      className={`tile${hi ? ' hi' : ''}${view === key ? ' active' : ''}`}
      aria-pressed={view === key}
      onClick={() => setParams(view === key ? {} : { view: key })}
    >
      <div className="mono" style={{ fontSize: 22, fontWeight: 600 }}>
        {n ?? '–'}
      </div>
      <div style={{ fontSize: 12, fontWeight: 600, color: hi ? undefined : 'var(--muted)' }}>{VIEWS[key]}</div>
    </button>
  )

  return (
    <>
      <div className="hdr" style={{ padding: '14px 16px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="home-top" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Logo />
          {!isAdmin && (
            <button type="button" className="gps-refresh" onClick={() => navigate('/dashboard')}>
              Dashboard
            </button>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div className="hdr-sub">
              {staff?.full_name} · {ROLE[staff?.role ?? ''] ?? ''}
            </div>
            <div style={{ fontSize: 24, fontWeight: 700, marginTop: 2 }}>{viewingMine ? 'My customers' : 'Team customers'}</div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div className={`hdr-pill ${syncPill.cls}`} title="Sync status">
              <IconCloud /> {syncPill.text}
            </div>
            <button
              className="icon-btn"
              style={{ width: 36, height: 36, color: 'var(--muted)' }}
              aria-label="Sign out"
              onClick={() => confirm('Sign out?') && logout()}
            >
              <IconPower />
            </button>
          </div>
        </div>
        {isAdmin && (
          <div className="pillseg" role="tablist" aria-label="Whose customers">
            <button role="tab" aria-selected={scope === 'mine'} className={scope === 'mine' ? 'on' : ''} onClick={() => setScope('mine')}>
              My work
            </button>
            <button role="tab" aria-selected={scope === 'all'} className={scope === 'all' ? 'on' : ''} onClick={() => setScope('all')}>
              Team work
            </button>
          </div>
        )}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,minmax(0,1fr))', gap: 8 }}>
          {tile('followups', fus?.counts.today ?? summary?.follow_ups_today, true)}
          {tile('overdue', fus?.counts.overdue ?? summary?.overdue)}
        </div>
      </div>

      <div className="home-controls" style={{ padding: '14px 16px 0', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div className="box search" style={{ color: 'var(--navy)' }}>
          <IconSearch />
          <label className="sr" htmlFor="h-search">
            Search leads
          </label>
          <input autoComplete="off"
            id="h-search"
            type="search"
            placeholder="Business name or POC…"
            style={{ fontWeight: 500 }}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        {view && (
          <div className="view-head">
            <div>
              <div className="page-title">{VIEWS[view]}</div>
              <div className="page-sub">{fus ? (view === 'followups' ? fus.counts.today : fus.counts.overdue) : '–'} in total</div>
            </div>
            <button type="button" className="gps-refresh" onClick={() => setParams({})}>
              Close
            </button>
          </div>
        )}
        {!view && (
        <div className="pillseg" role="tablist" aria-label="Lead status">
          <button
            role="tab"
            aria-selected={tab === 'not_converted'}
            className={tab === 'not_converted' ? 'on' : ''}
            onClick={() => setParams({})}
          >
            Meetings ({summary?.not_converted ?? '–'})
          </button>
          <button
            role="tab"
            aria-selected={tab === 'converted'}
            className={tab === 'converted' ? 'on' : ''}
            onClick={() => setParams({ tab: 'converted' })}
          >
            Leads ({summary?.converted ?? '–'})
          </button>
          <button role="tab" aria-selected={tab === 'deals'} className={tab === 'deals' ? 'on' : ''} onClick={() => setParams({ tab: 'deals' })}>
            Deals
          </button>
        </div>
        )}
        {!view && tab === 'not_converted' && (
          <div className="hs" role="tablist" aria-label="Meeting with">
            {KINDS.map((k) => (
              <button
                key={k.key}
                role="tab"
                aria-selected={kind === k.key}
                className={`sub${kind === k.key ? ' on' : ''}`}
                onClick={() => setParams(k.key === 'customer' ? {} : { kind: k.key })}
              >
                {k.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="scroll" style={{ paddingTop: 12, gap: 10 }}>
        {view ? (
          <FollowUpView
            when={view === 'followups' ? 'today' : 'overdue'}
            fus={fus}
            query={query}
            canAct={viewingMine}
            onChanged={() => {
              loadFus()
              setTick((n) => n + 1)
            }}
          />
        ) : tab === 'deals' ? (
          <DealsView query={query} showSM={!viewingMine} mine={!!mineQ} />
        ) : list === null ? (
          <div className="empty">Loading…</div>
        ) : items.length === 0 ? (
          <EmptyState
            text={
              !viewingMine && !view
                ? 'No customers yet.'
                : view === 'followups'
                ? 'No follow-ups today.'
                : view === 'overdue'
                  ? 'Nothing is overdue.'
                  : tab === 'converted'
                ? 'Customers you recommend as Proceed show up here as Leads.'
                : kind === 'customer'
                  ? 'No meetings yet. Tap “New meeting” to add your first one.'
                  : `No ${kind} meetings yet. Tap “New meeting” to add one.`
            }
          />
        ) : (
          <div className="lead-grid">
            {items.map((c) => (
              <LeadCard key={c.id} c={c} />
            ))}
          </div>
        )}
      </div>

      {/* Leads are created by a meeting (Proceed), so the Leads tab has no "new" button: open a lead to add a meeting. */}
      {viewingMine && (view || tab === 'not_converted') && (
        <div className="foot">
          <div className="inner">
            <button className="btn primary" style={{ width: '100%', height: 56, fontSize: 17 }} onClick={() => navigate('/new-meeting')}>
              <IconPlus /> New meeting
            </button>
          </div>
        </div>
      )}
    </>
  )
}

// Shown when a list is empty: a small illustration and one line of text.
function EmptyState({ text }: { text: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18, padding: '36px 24px', textAlign: 'center' }}>
      <svg width="124" height="112" viewBox="0 0 124 112" aria-hidden="true">
        <circle cx="50" cy="58" r="44" fill="#E3EAF0" />
        {/* calendar */}
        <rect x="74" y="12" width="40" height="42" rx="6" fill="#fff" stroke="#8FA6B8" strokeWidth="2" />
        <rect x="74" y="12" width="40" height="11" rx="6" fill="#12263A" />
        <rect x="74" y="18" width="40" height="5" fill="#12263A" />
        {[0, 1, 2].map((r) =>
          [0, 1, 2].map((c) => (
            <circle key={`${r}${c}`} cx={83 + c * 11} cy={32 + r * 8.5} r="2.2" fill={r === 0 && c === 2 ? '#F2A93B' : '#8FA6B8'} />
          )),
        )}
        {/* person: short hair, shirt and tie */}
        <path d="M20 104c0-19 13-30 30-30s30 11 30 30z" fill="#7C97AD" />
        <path d="M43 75l7 9 7-9z" fill="#fff" />
        <path d="M48 82h4l2 22h-8z" fill="#12263A" />
        <rect x="44" y="64" width="12" height="12" rx="4" fill="#E9C3A4" />
        <ellipse cx="50" cy="48" rx="15" ry="17" fill="#F2D3B8" />
        <path d="M34 46c-2-17 8-26 17-26s19 8 15 26c-2-6-4-9-8-10-8 3-17 3-24 0-1 3-1 6 0 10z" fill="#2F3E4E" />
        <circle cx="44" cy="50" r="1.6" fill="#2F3E4E" />
        <circle cx="56" cy="50" r="1.6" fill="#2F3E4E" />
        <path d="M45 58c3 3 7 3 10 0" fill="none" stroke="#B5785A" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
      <div style={{ fontSize: 17, fontWeight: 500, color: 'var(--navy)', maxWidth: 240, lineHeight: 1.4 }}>{text}</div>
    </div>
  )
}

export function LeadCard({ c }: { c: CustomerCard }) {
  const { staff } = useAuth()
  const grade = c.opportunity_grade?.[0]
  const sub = [c.business_name ? c.promoter : null, c.location].filter(Boolean).join(' · ')
  const need = [c.loan_required ? `₹${formatINR(c.loan_required)}` : null, c.purpose].filter(Boolean)
  const when = c.next_action_date ? nextActionWhen(c.next_action_date) : null
  const next = [c.next_action, when?.text].filter(Boolean).join(' · ')
  return (
    <Link to={`/customers/${c.id}`} className="lead">
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--navy)' }}>{displayName(c)}</div>
          {sub && <div style={{ fontSize: 13, color: 'var(--muted)' }}>{sub}</div>}
          {staff?.role !== 'SM' && c.owner_name && c.owner_name !== staff?.full_name && <div style={{ fontSize: 12, color: 'var(--muted)' }}>Sales manager: {c.owner_name}</div>}
        </div>
        {grade && GRADE_COLORS[grade] && (
          <div className="mono grade" style={{ background: GRADE_COLORS[grade][0], color: GRADE_COLORS[grade][1] }}>
            {grade}
          </div>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', gap: 8 }}>
        <div style={{ fontSize: 14, fontWeight: 600 }}>
          {need.length ? (
            <>
              {c.loan_required && <span className="mono">₹{formatINR(c.loan_required)}</span>}
              {c.loan_required && c.purpose && ' · '}
              {c.purpose}
            </>
          ) : null}
        </div>
        {c.conversion_status === 'CONVERTING' ? (
          <div className="status-pill" style={{ background: '#FDF1DC', color: '#8a5a00' }}>
            <span className="spinner-ring sm" aria-hidden />
            Converting…
          </div>
        ) : c.conversion_status === 'CONVERSION_FAILED' ? (
          <div className="status-pill" style={{ background: '#FBE7DB', color: 'var(--warn)' }}>Conversion failed</div>
        ) : (
          (c.loan_stage || c.status) && <div className="status-pill">{c.loan_stage ?? c.status}</div>
        )}
      </div>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          fontSize: 13,
          fontWeight: 600,
          color: !next ? 'var(--muted)' : when?.late ? 'var(--warn)' : 'var(--good)',
        }}
      >
        <IconCal /> {next || 'No next visit set'}
      </div>
    </Link>
  )
}

// A tile's list: the follow-ups themselves, meetings (prospects) and leads in two separate sections.
function FollowUpView({
  when,
  fus,
  query,
  canAct,
  onChanged,
}: {
  when: 'today' | 'overdue'
  fus: FollowUpList | null
  query: string
  canAct: boolean
  onChanged: () => void
}) {
  if (!fus) return <div className="empty">Loading…</div>
  const q = query.trim().toLowerCase()
  const rows = fus.items.filter(
    (f) => f.when === when && (!q || [f.customer.business_name, f.customer.promoter].some((x) => (x ?? '').toLowerCase().includes(q))),
  )
  if (rows.length === 0) return <EmptyState text={when === 'today' ? 'No follow-ups today.' : 'Nothing is overdue.'} />
  return (
    <>
      {[
        { title: 'Meetings', rows: rows.filter((f) => !f.customer.converted) },
        { title: 'Leads', rows: rows.filter((f) => f.customer.converted) },
      ]
        .filter((section) => section.rows.length > 0)
        .map((section) => (
          <section key={section.title} className="list-section" aria-label={section.title}>
            <div className="list-title">
              {section.title} <span className="list-count">{section.rows.length}</span>
            </div>
            <div className="lead-grid">
              {section.rows.map((f) => (
                <FollowUpCard key={f.id} f={f} canAct={canAct} onChanged={onChanged} />
              ))}
            </div>
          </section>
        ))}
    </>
  )
}

// The Deals tab: what the leads became in Zoho. Read-only; the operations team updates deals in Zoho.
function DealsView({ query, showSM, mine }: { query: string; showSM: boolean; mine: boolean }) {
  const [data, setData] = useState<DealList | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    api<DealList>(mine ? '/deals?mine=true' : '/deals')
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(e instanceof ApiError && typeof e.detail === 'string' ? e.detail : 'Could not load the deals. Try again.'))
    return () => {
      cancelled = true
    }
  }, [mine])
  if (error) return <div className="err">{error}</div>
  if (!data) return <div className="empty">Loading deals from Zoho…</div>
  const q = query.trim().toLowerCase()
  const rows = data.items.filter((d) => !q || [d.business_name, d.promoter, d.deal.name].some((x) => (x ?? '').toLowerCase().includes(q)))
  if (!data.zoho) return <EmptyState text="Deals come from Zoho, which is not connected here." />
  if (rows.length === 0)
    return <EmptyState text={data.items.length ? 'No deals match your search.' : 'No deals yet. A lead shows here once it has been converted to a deal in Zoho.'} />
  return (
    <div className="lead-grid">
      {rows.map((d) => (
        <DealCard key={d.customer_id} d={d} showSM={showSM} />
      ))}
    </div>
  )
}
