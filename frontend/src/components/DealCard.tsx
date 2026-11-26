// A deal, read-only. Whatever operations do in Zoho (stage, amount, next step) shows here on the next refresh.

import { Link } from 'react-router-dom'
import type { DealItem } from '../api'
import { displayName, formatINR } from '../format'

export const stageColors = (stage: string | null): [string, string] =>
  stage === 'Closed Won' ? ['#E3F1E9', '#1F6F4A'] : (stage ?? '').startsWith('Closed Lost') ? ['#FBE7DB', '#9F1D1D'] : ['#E7ECF1', '#12263A']

export default function DealCard({ d, showSM }: { d: DealItem; showSM: boolean }) {
  const [bg, fg] = stageColors(d.deal.stage)
  const name = displayName({ business_name: d.business_name, promoter: d.promoter, lead_ref: 'Customer' })
  return (
    <Link to={`/customers/${d.customer_id}?from=deals`} className="lead">
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--navy)' }}>{name}</div>
          {d.deal.name && d.deal.name !== name && <div style={{ fontSize: 13, color: 'var(--muted)' }}>Deal: {d.deal.name}</div>}
          {showSM && d.sm_name && <div style={{ fontSize: 12, color: 'var(--muted)' }}>Sales manager: {d.sm_name}</div>}
        </div>
        {d.deal.stage && (
          <div className="status-pill" style={{ background: bg, color: fg }}>
            {d.deal.stage}
          </div>
        )}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', gap: 8, fontSize: 14, fontWeight: 600 }}>
        <span className="mono">{d.deal.amount != null ? `₹${formatINR(d.deal.amount)}` : '—'}</span>
        {d.deal.closing_date && <span className="muted">Closing {d.deal.closing_date}</span>}
      </div>
      {d.deal.next_step && (
        <div className="muted" style={{ fontSize: 13 }}>
          Next step: {d.deal.next_step}
        </div>
      )}
    </Link>
  )
}
