// A full-screen stop sign: the app cannot record a meeting (or add a lead) unless the phone's
// location is switched on. It cannot be dismissed; the only ways out are "Try again" and "Back".

import type { GpsErrorCode } from '../gps'

// Errors that mean "location is off or blocked". (A timeout means it is on but has no fix yet.)
export const LOCATION_OFF: GpsErrorCode[] = ['denied', 'unavailable', 'unsupported', 'insecure']

// One short line on what to do, for each reason the location is off.
const HINT: Partial<Record<GpsErrorCode, string>> = {
  denied: 'Allow location for this app in your phone settings.',
  unavailable: 'Switch on Location (GPS) on your phone.',
  insecure: 'Open the app over a secure (https) link.',
  unsupported: 'This browser cannot read the location.',
}

export function LocationGate({ error, onRetry, onBack }: { error: GpsErrorCode; onRetry: () => void; onBack: () => void }) {
  return (
    <div className="sheet-bg" style={{ zIndex: 30, alignItems: 'center', padding: 22 }} role="alertdialog" aria-modal="true" aria-labelledby="loc-title">
      <div className="card" style={{ padding: 22, display: 'flex', flexDirection: 'column', gap: 10, width: '100%' }}>
        <div style={{ fontSize: 34, lineHeight: 1 }} aria-hidden="true">
          📍
        </div>
        <div className="sheet-title" id="loc-title">
          Turn on your location
        </div>
        <div style={{ fontSize: 14, color: 'var(--ink)', lineHeight: 1.4 }}>
          A meeting or lead can't be recorded without it. {HINT[error]}
        </div>
        <button className="btn primary" style={{ marginTop: 6 }} onClick={onRetry}>
          Try again
        </button>
        <button className="btn ghost" style={{ border: 'none' }} onClick={onBack}>
          Go back
        </button>
      </div>
    </div>
  )
}
