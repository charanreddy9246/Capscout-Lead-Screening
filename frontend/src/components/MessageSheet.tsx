// "Message": a draft written from the customer's Next Action. The SM edits it and sends it from their own
// WhatsApp or SMS app, or copies it. The app never sends anything itself; each send is recorded on the customer.

import { useEffect, useState } from 'react'
import { api, ApiError, post, type MessageDraft } from '../api'

type Channel = 'WHATSAPP' | 'SMS' | 'COPY'

export function MessageButton({ customerId, onSent, label = 'WhatsApp / SMS message' }: { customerId: string; onSent?: () => void; label?: string }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" className="gps-refresh" onClick={() => setOpen(true)}>
        {label}
      </button>
      {open && <MessageSheet customerId={customerId} onClose={() => setOpen(false)} onSent={onSent} />}
    </>
  )
}

function MessageSheet({ customerId, onClose, onSent }: { customerId: string; onClose: () => void; onSent?: () => void }) {
  const [draft, setDraft] = useState<MessageDraft | null>(null)
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  useEffect(() => {
    api<MessageDraft>(`/customers/${customerId}/messages/draft`)
      .then((d) => {
        setDraft(d)
        setText(d.text)
      })
      .catch(() => setError('Could not prepare the message. Try again.'))
  }, [customerId])

  const mobile = (draft?.mobile ?? '').replace(/\D/g, '').slice(-10)
  const canPhone = mobile.length === 10

  async function send(channel: Channel) {
    const body = text.trim()
    if (!body) return
    setError(null)
    if (channel === 'WHATSAPP') window.open(`https://wa.me/91${mobile}?text=${encodeURIComponent(body)}`, '_blank', 'noopener')
    if (channel === 'SMS') window.location.href = `sms:+91${mobile}?body=${encodeURIComponent(body)}`
    if (channel === 'COPY') {
      try {
        await navigator.clipboard.writeText(body)
        setNote('Copied. Paste it into any app.')
      } catch {
        setNote('Could not copy. Select the text and copy it.')
        return
      }
    }
    try {
      await post(`/customers/${customerId}/messages`, { channel, body })
      onSent?.()
      if (channel !== 'COPY') onClose()
    } catch (e) {
      setError(e instanceof ApiError && typeof e.detail === 'string' ? e.detail : 'Sent, but it could not be recorded.')
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Message to the customer"
      style={{ position: 'absolute', inset: 0, zIndex: 50, background: 'rgba(18,38,58,0.45)', display: 'flex', alignItems: 'flex-end' }}
      onClick={onClose}
    >
      <div style={{ background: '#fff', width: '100%', borderRadius: '16px 16px 0 0', padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div className="h">Message{draft?.next_action ? ` · ${draft.next_action}` : ''}</div>
          <button type="button" className="gps-refresh" onClick={onClose}>
            Close
          </button>
        </div>
        {!draft && !error && <div className="empty">Preparing…</div>}
        {draft && (
          <>
            <label className="lbl" htmlFor="msg-text">
              Edit before sending
            </label>
            <textarea id="msg-text" className="fld" style={{ height: 150, resize: 'none', padding: '10px 12px' }} value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} />
            {!canPhone && <div className="muted" style={{ fontSize: 13 }}>This customer has no mobile number yet, so only Copy is available.</div>}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button type="button" className="gps-refresh" disabled={!canPhone || !text.trim()} onClick={() => send('WHATSAPP')}>
                WhatsApp
              </button>
              <button type="button" className="gps-refresh" disabled={!canPhone || !text.trim()} onClick={() => send('SMS')}>
                SMS
              </button>
              <button type="button" className="gps-refresh" disabled={!text.trim()} onClick={() => send('COPY')}>
                Copy
              </button>
            </div>
            <div className="muted" style={{ fontSize: 12 }}>
              It opens in your own app and you press send there. Check the wording first.
            </div>
          </>
        )}
        {note && <div style={{ fontSize: 13, color: 'var(--good)' }}>{note}</div>}
        {error && <div className="err">{error}</div>}
      </div>
    </div>
  )
}
