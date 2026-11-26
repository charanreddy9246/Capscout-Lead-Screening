// Customer / lead overview: current progress by step and full meeting history.
// Not in the prototype, so it is built from the prototype's components.

import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, ApiError, post, type CustomerDetail, type DealList, type SentMessage } from '../api'
import { stageColors } from '../components/DealCard'
import { formatINR } from '../format'
import { useAuth } from '../auth'
import { IconArrow, IconBack } from '../components/icons'
import MeetingHistory from '../components/MeetingHistory'
import { displayName, relativeDay } from '../format'
import { useFieldCatalog } from '../fields'
import { MessageButton } from '../components/MessageSheet'
import { friendlyZohoError } from '../zohoErrors'
import { loadDraft } from '../meetingDraft'

const STATUS_LABEL: Record<CustomerDetail['conversion_status'], string> = {
  NOT_CONVERTED: 'Prospect',
  CONVERTING: 'Converting…',
  CONVERTED: 'Converted Lead',
  CONVERSION_FAILED: 'Conversion failed',
}
const SLOW_AFTER_MS = 20_000 // a normal conversion finishes in a few seconds

export default function CustomerPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const fromDeals = useSearchParams()[0].get('from') === 'deals' // opened from the Deals tab: view only
  const [c, setC] = useState<CustomerDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showCount, setShowCount] = useState(false)
  const [msgTick, setMsgTick] = useState(0) // bumped when a message is sent, to refresh the log
  const [retrying, setRetrying] = useState(false)
  const [convertError, setConvertError] = useState<string | null>(null)

  // "Retry conversion" after a failure: no new form, the details confirmed earlier are kept.
  async function retryConversion() {
    setRetrying(true)
    setConvertError(null)
    try {
      setC(await post<CustomerDetail>(`/customers/${id}/convert`))
    } catch (e) {
      setConvertError(
        e instanceof ApiError && e.status === 0
          ? 'No connection. Converting to a Lead needs the internet. Try again when you have signal.'
          : 'Could not start the conversion. Try again.',
      )
    } finally {
      setRetrying(false)
    }
  }

  useEffect(() => {
    api<CustomerDetail>(`/customers/${id}`)
      .then(setC)
      .catch((e) => setError(e instanceof ApiError && e.status === 404 ? 'Lead not found.' : 'Could not load this lead.'))
  }, [id])

  // While Zoho is creating the Lead, check again every few seconds so the screen updates by itself.
  const converting_ = c?.conversion_status === 'CONVERTING'
  // A normal conversion takes seconds. After SLOW_AFTER_MS we tell the user it is taking longer.
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    if (!converting_) return
    const t = setTimeout(() => setSlow(true), SLOW_AFTER_MS)
    return () => {
      clearTimeout(t)
      setSlow(false)
    }
  }, [converting_])
  useEffect(() => {
    if (!converting_) return
    const t = setInterval(() => {
      api<CustomerDetail>(`/customers/${id}?quiet=true`).then(setC).catch(() => undefined)
    }, 3000)
    return () => clearInterval(t)
  }, [converting_, id])

  const converted = c?.conversion_status === 'CONVERTED'
  const { staff } = useAuth()
  const isOwner = !!c && !!staff && c.owner.id === staff.id // anyone can look at it (by role); only its owner changes it
  const back = () => (isOwner || staff?.role === 'SM' ? navigate(fromDeals ? '/?tab=deals' : converted ? '/?tab=converted' : '/') : navigate(-1))
  const hasDraft = loadDraft(id) !== null

  return (
    <>
      <div className="hdr" style={{ padding: '10px 12px 14px', display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <button className="icon-btn" aria-label="Back to my leads" onClick={back}>
            <IconBack />
          </button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 17, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {c ? displayName(c) : 'Lead'}
            </div>
            <div className="mono" style={{ fontSize: 12, color: 'var(--muted)' }}>
              {c ? `${c.lead_ref} · ${STATUS_LABEL[c.conversion_status]}` : ''}
            </div>
          </div>
        </div>
      </div>

      <div className="scroll">
        {error && <div className="err">{error}</div>}
        {!c && !error && <div className="empty">Loading…</div>}
        {c && (
          <>
            {c.conversion_status === 'CONVERTED' && <DealInfo customerId={id} />}
            {c.conversion_status === 'CONVERTED' && <LoanJourney stage={c.loan_stage ?? null} />}
            <div className="card" style={{ padding: '14px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {(c.promoter || c.mobile) && (
                <div style={{ fontSize: 14, color: 'var(--muted)' }}>
                  {[c.business_name ? c.promoter : null, c.mobile ? `+91 ${c.mobile}` : null].filter(Boolean).join(' · ')}
                </div>
              )}
              {isOwner && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div className="lbl" style={{ margin: 0 }}>
                    Contact customer
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <MessageButton customerId={id} onSent={() => setMsgTick((n) => n + 1)} />
                    {c.mobile && (
                      <a className="gps-refresh" href={`tel:+91${c.mobile}`} style={{ textDecoration: 'none' }}>
                        Call
                      </a>
                    )}
                  </div>
                </div>
              )}
              {c.zoho_lead_id && (
                <div className="mono" style={{ fontSize: 13, color: 'var(--good)', fontWeight: 600 }}>
                  Lead ID: {c.zoho_lead_id}
                </div>
              )}
              {/* Percentage by default; tap for "32 / 41 completed". */}
              <button className="progress-btn" onClick={() => setShowCount((s) => !s)} aria-label={`${c.progress.filled} of ${c.progress.total} fields completed`}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14, fontWeight: 600 }}>
                  <span>Fields collected</span>
                  <span className="mono" style={{ color: 'var(--navy)' }}>
                    {showCount ? `${c.progress.filled} / ${c.progress.total} completed` : `${c.progress.percent}%`}
                  </span>
                </div>
                <div className="bar">
                  <span style={{ width: `${c.progress.percent}%` }} />
                </div>
              </button>
              <div style={{ fontSize: 13, color: 'var(--muted)' }}>
                {c.meeting_count} meeting{c.meeting_count === 1 ? '' : 's'} · Last: {relativeDay(c.last_meeting_at)}
              </div>
            </div>

            {convertError && <div className="err">{convertError}</div>}
            <ConversionPanel
              c={c}
              slow={slow}
              retrying={retrying}
              onRetry={retryConversion}
            />

              <MessageLog customerId={id} refreshKey={msgTick} />
              <div className="h" style={{ marginTop: 4 }}>
                Meeting history
              </div>
              <MeetingHistory customerId={id} reloadKey={`${c.meeting_count}:${c.conversion_status}`} />
          </>
        )}
      </div>

      <div className="foot">
        <div className="inner">
          <button className="btn ghost" style={fromDeals ? { flex: 1 } : { flex: 'none', width: 104 }} onClick={back}>
            Back
          </button>
          {isOwner && !fromDeals && ( // a deal is changed by the operations team; the meeting continues from the lead
          <button
            className="btn primary"
            style={{ flex: 1 }}
            disabled={!c}
            onClick={() => navigate(`/customers/${id}/meeting`)}
          >
            Next meeting
            {hasDraft && (
              <span className="tag warn" style={{ marginLeft: 2 }}>
                Draft
              </span>
            )}{' '}
            <IconArrow />
          </button>
          )}
        </div>
      </div>
    </>
  )
}

// Where the conversion to a Lead is. (A prospect becomes a Lead when a meeting is saved with the
// recommendation "Proceed"; there is no separate button.)
function ConversionPanel({
  c,
  slow: slowLocal,
  retrying,
  onRetry,
}: {
  c: CustomerDetail
  slow: boolean
  retrying: boolean
  onRetry: () => void
}) {
  if (c.conversion_status === 'CONVERTING') {
    // Normally a few seconds. If it is taking longer (or Zoho already failed once and is retrying),
    // say so, and tell the user it is safe to close the app and check back later.
    const slow = c.lead_sync_attempts > 0 || slowLocal
    return (
      <div className="card" style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: 8 }} role="status">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="spinner-ring" aria-hidden />
          <div style={{ fontSize: 15, fontWeight: 700, color: slow ? 'var(--warn)' : '#8a5a00' }}>
            {slow ? 'Still converting to Lead…' : 'Converting to Lead…'}
          </div>
        </div>
        {slow ? (
          <div style={{ fontSize: 13, color: 'var(--ink)' }}>
            This is taking longer than usual and may take <strong>up to 5 minutes</strong>. You can safely{' '}
            <strong>close the app and check again after 5 minutes</strong>. It will finish on its own and the lead will
            then move to Leads.
          </div>
        ) : (
          <div style={{ fontSize: 13, color: 'var(--muted)' }}>Saving as a Lead. This usually takes a few seconds.</div>
        )}
        {c.lead_sync_status === 'FAILED' && c.lead_sync_error && (
          <div style={{ fontSize: 12, color: 'var(--warn)', fontWeight: 600 }}>
            {friendlyZohoError(c.lead_sync_error)}
          </div>
        )}
      </div>
    )
  }
  if (c.conversion_status === 'CONVERSION_FAILED')
    return (
      <div className="card" style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--warn)' }}>Conversion failed</div>
        {c.lead_sync_error && <div style={{ fontSize: 13, color: 'var(--muted)' }}>{friendlyZohoError(c.lead_sync_error)}</div>}
        <button className="btn ghost" style={{ width: '100%' }} disabled={retrying} onClick={onRetry}>
          {retrying ? 'Retrying…' : 'Retry conversion'}
        </button>
      </div>
    )
  return null
}

// Where a converted Lead has got to. The stage is chosen in a meeting ("Loan Stage" on the last step).
function LoanJourney({ stage }: { stage: string | null }) {
  const catalog = useFieldCatalog()
  const stages = catalog?.fields.find((f) => f.key === 'next_action')?.options ?? []
  const at = stage ? stages.indexOf(stage) : -1
  return (
    <div className="card" style={{ padding: '14px 14px' }}>
      <div className="h" style={{ marginBottom: 10 }}>
        Loan journey
      </div>
      <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {stages.map((s, i) => {
          const done = i < at
          const cur = i === at
          return (
            <li key={s} aria-current={cur ? 'step' : undefined} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 14, fontWeight: cur ? 800 : 600, color: done || cur ? 'var(--navy)' : 'var(--muted)' }}>
              <span className={`step-dot${cur ? ' cur' : ''}${done ? ' done' : ''}`} aria-hidden style={{ flex: 'none' }}>
                {done ? '✓' : i + 1}
              </span>
              {s}
            </li>
          )
        })}
      </ol>
      {at < 0 && <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>Not started. Pick the Loan Stage in your next meeting.</div>}
    </div>
  )
}

// What has been sent to this customer (everyone who can see the customer can read it).
function MessageLog({ customerId, refreshKey }: { customerId: string; refreshKey: number }) {
  const [items, setItems] = useState<SentMessage[] | null>(null)
  useEffect(() => {
    api<{ items: SentMessage[] }>(`/customers/${customerId}/messages`).then((d) => setItems(d.items)).catch(() => undefined)
  }, [customerId, refreshKey])
  if (!items || items.length === 0) return null
  const label = { WHATSAPP: 'WhatsApp', SMS: 'SMS', COPY: 'Copied' } as const
  return (
    <details className="card" style={{ padding: 14 }}>
      <summary className="h" style={{ cursor: 'pointer' }}>
        Message history ({items.length})
      </summary>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 10 }}>
        {items.map((m) => (
          <div key={m.id} style={{ fontSize: 13 }}>
            <div className="muted">
              {label[m.channel]} · {new Date(m.sent_at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}
              {m.by ? ` · ${m.by}` : ''}
            </div>
            <div>{m.body}</div>
          </div>
        ))}
      </div>
    </details>
  )
}

// The deal this lead became in Zoho. Read-only: the operations team changes it in Zoho.
function DealInfo({ customerId }: { customerId: string }) {
  const [deal, setDeal] = useState<DealList['items'][number]['deal'] | null>(null)
  useEffect(() => {
    api<DealList>(`/deals?customer_id=${customerId}`).then((d) => setDeal(d.items[0]?.deal ?? null)).catch(() => undefined)
  }, [customerId])
  if (!deal) return null
  const [bg, fg] = stageColors(deal.stage)
  return (
    <div className="card" style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <div className="h">Deal</div>
        {deal.stage && (
          <div className="status-pill" style={{ background: bg, color: fg }}>
            {deal.stage}
          </div>
        )}
      </div>
      {deal.name && <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--navy)' }}>{deal.name}</div>}
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14, fontWeight: 600 }}>
        <span className="mono">{deal.amount != null ? `₹${formatINR(deal.amount)}` : '—'}</span>
        {deal.closing_date && <span className="muted">Closing {deal.closing_date}</span>}
      </div>
      {deal.next_step && <div className="muted" style={{ fontSize: 13 }}>Next step: {deal.next_step}</div>}
      <div className="muted" style={{ fontSize: 12 }}>Managed by the operations team in Zoho. You can view it here but not change it.</div>
    </div>
  )
}
