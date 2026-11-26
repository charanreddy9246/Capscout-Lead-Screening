// ONE dashboard screen for everyone. The server decides whose numbers it gets:
//   SM    -> their own ("My dashboard")
//   Admin -> the whole team, and tapping a sales manager opens that person's dashboard (the same screen)

import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, type CustomerCard, type CustomerList, type DashboardData, type DashboardMember } from '../api'
import { useAuth } from '../auth'
import AdminShell from '../components/AdminShell'
import { IconBack } from '../components/icons'
import { isoDate, relativeDay } from '../format'
import { LeadCard } from './Home'

const PERIODS = [
  { key: 'today', label: 'Today' },
  { key: 'week', label: '7 days' },
  { key: 'month', label: '30 days' },
] as const
type PeriodKey = (typeof PERIODS)[number]['key']

export default function Dashboard() {
  const { staff } = useAuth()
  const navigate = useNavigate()
  const { staffId } = useParams()
  const isSM = staff?.role === 'SM'
  const [period, setPeriod] = useState<PeriodKey>('week')
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [customers, setCustomers] = useState<{ meetings: CustomerCard[]; leads: CustomerCard[] } | null>(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    const q = new URLSearchParams({ period, today: isoDate(new Date()) })
    if (staffId) q.set('staff_id', staffId)
    api<DashboardData>(`/dashboard?${q}`)
      .then((d) => !cancelled && setData(d))
      .catch(() => !cancelled && setError('Could not load the dashboard. Try again.'))
    return () => {
      cancelled = true
    }
  }, [period, staffId])

  // An Admin looking at one sales manager also sees that person's customers.
  useEffect(() => {
    if (!staffId || isSM) return
    let cancelled = false
    Promise.all(
      (['not_converted', 'converted'] as const).map((tab) =>
        api<CustomerList>(`/customers?tab=${tab}&staff_id=${staffId}&limit=200`).then((d) => d.items),
      ),
    )
      .then(([meetings, leads]) => !cancelled && setCustomers({ meetings, leads }))
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [staffId, isSM])

  const title = data?.scope === 'team' ? 'Team dashboard' : isSM ? 'My dashboard' : (data?.person?.full_name ?? 'Dashboard')

  const body = (
    <>
      <div className="page-fixed">
        <div className="page-head">
          <div>
            <div className="page-title">{title}</div>
            <div className="page-sub">
              {data?.scope === 'team' ? 'All sales managers' : data?.scope === 'person' ? 'Sales manager' : 'Your own numbers'}
            </div>
          </div>
        </div>
        <div className="pillseg" role="tablist" aria-label="Period">
          {PERIODS.map((p) => (
            <button key={p.key} role="tab" aria-selected={period === p.key} className={period === p.key ? 'on' : ''} onClick={() => setPeriod(p.key)}>
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div className="scroll">
        {error && <div className="err">{error}</div>}
        {!data && !error && <div className="empty">Loading…</div>}
        {data && (
          <>
            <div className="stat-grid">
              <Stat label="Meetings" n={data.totals.meetings} />
              <Stat label="New prospects" n={data.totals.new_prospects} />
              <Stat label="Leads converted" n={data.totals.leads_converted} />
              <Stat label="Open customers" n={data.totals.open_customers} />
              <Stat label="Follow-ups today" n={data.totals.follow_ups_today} />
              <Stat label="Overdue" n={data.totals.overdue} warn />
              <Stat label="Meetings without GPS" n={data.totals.no_gps} warn />
              <Stat label="Failed syncs" n={data.totals.sync_failed} warn />
            </div>

            {data.lead_stages?.some((s) => s.count > 0) && (
              <section className="list-section" aria-label="Leads by loan stage">
                <div className="list-title">Leads by loan stage</div>
                <div className="pipeline">
                  {data.lead_stages.map((p) => (
                    <div key={p.label} className="bar-row">
                      <div className="bar-label">{p.label}</div>
                      <div className="bar-track">
                        <span style={{ width: `${Math.max(p.count ? 6 : 0, (p.count / Math.max(1, ...data.lead_stages.map((x) => x.count))) * 100)}%` }} />
                      </div>
                      <div className="bar-n mono">{p.count}</div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {data.scope === 'team' && data.members && (
              <section className="list-section" aria-label="Sales managers">
                <div className="list-title">
                  Sales managers <span className="list-count">{data.members.length}</span>
                </div>
                {data.members.length === 0 && <div className="empty">No sales managers yet.</div>}
                {/* phones and tablets: cards; laptops: a table with one column per number */}
                <div className="lead-grid members-cards">
                  {data.members.map((m) => (
                    <MemberRow key={m.id} m={m} onOpen={() => navigate(`/dashboard/${m.id}`)} />
                  ))}
                </div>
              </section>
            )}

            {data.scope === 'person' && customers && (
              <>
                {[
                  { title: 'Meetings', rows: customers.meetings },
                  { title: 'Leads', rows: customers.leads },
                ].map((section) => (
                  <section key={section.title} className="list-section" aria-label={section.title}>
                    <div className="list-title">
                      {section.title} <span className="list-count">{section.rows.length}</span>
                    </div>
                    {section.rows.length === 0 && <div className="muted" style={{ fontSize: 14 }}>None.</div>}
                    <div className="lead-grid">
                      {section.rows.map((c) => (
                        <LeadCard key={c.id} c={c} />
                      ))}
                    </div>
                  </section>
                ))}
              </>
            )}
          </>
        )}
      </div>
    </>
  )

  if (isSM)
    return (
      <>
        <div className="hdr back-hdr" style={{ padding: '10px 12px 6px', display: 'flex', alignItems: 'center', gap: 6 }}>
          <button className="icon-btn" aria-label="Back to my customers" onClick={() => navigate('/')}>
            <IconBack />
          </button>
          <div style={{ fontSize: 17, fontWeight: 700 }}>Dashboard</div>
        </div>
        {body}
      </>
    )

  return (
    <AdminShell>
      <div style={{ padding: '0 18px 8px' }}>
        {staffId ? (
          <button type="button" className="gps-refresh" onClick={() => navigate('/dashboard')}>
            <IconBack /> {staffId === staff?.id ? 'Back to the team' : 'All sales managers'}
          </button>
        ) : (
          <button type="button" className="gps-refresh" onClick={() => navigate(`/dashboard/${staff?.id}`)}>
            My own numbers
          </button>
        )}
      </div>
      {body}
    </AdminShell>
  )
}

function Stat({ label, n, warn = false }: { label: string; n: number; warn?: boolean }) {
  return (
    <div className={`stat${warn && n > 0 ? ' warn' : ''}`}>
      <div className="mono stat-n">{n}</div>
      <div className="stat-l">{label}</div>
    </div>
  )
}

function MemberRow({ m, onOpen }: { m: DashboardMember; onOpen: () => void }) {
  return (
    <button type="button" className="lead" onClick={onOpen}>
      <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--navy)' }}>{m.full_name}</div>
      <div className="member-stats">
        <span>
          <b className="mono">{m.meetings}</b> meetings
        </span>
        <span>
          <b className="mono">{m.new_prospects}</b> prospects
        </span>
        <span>
          <b className="mono">{m.leads_converted}</b> leads
        </span>
        <span className={m.overdue ? 'bad' : ''}>
          <b className="mono">{m.overdue}</b> overdue
        </span>
        <span className={m.no_gps ? 'bad' : ''}>
          <b className="mono">{m.no_gps}</b> no GPS
        </span>
      </div>
      <div className="muted" style={{ fontSize: 13 }}>
        Last meeting: {m.last_meeting_at ? relativeDay(m.last_meeting_at) : 'none yet'}
      </div>
    </button>
  )
}
