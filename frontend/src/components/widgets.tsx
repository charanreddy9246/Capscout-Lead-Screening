// Form controls from the client's prototype. Options always come from the
// Excel (via the field catalogue); fields without an Excel dropdown are typed.

import { useEffect, useId, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { formatINR } from '../format'

type ChoiceProps = {
  label: string
  options: string[]
  value: string
  onChange: (v: string) => void
  kind?: 'wrap' | 'seg' | 'hs' | 'list' // 'list' always shows a dropdown list
  disabled?: boolean // greyed out and cannot be changed
}

// Tapping the selected option again clears it, so a wrong tap can be undone.
const LIST_FROM = 7 // short lists are tap buttons; longer ones are a dropdown list

export function Choice({ label, options, value, onChange, kind = 'wrap', disabled = false }: ChoiceProps) {
  const cls = kind === 'seg' ? 'sg' : 'chip'
  if (kind === 'list' || (kind === 'wrap' && options.length >= LIST_FROM)) {
    return <DropdownList label={label} options={options} value={value} onChange={onChange} disabled={disabled} />
  }
  return (
    <div>
      <div className="lbl">{label}</div>
      <div
        className="opts"
        style={{ gridTemplateColumns: `repeat(${options.length <= 3 ? options.length : options.length === 4 ? 2 : 3}, minmax(0, 1fr))` }}
        role="radiogroup"
        aria-label={label}
      >
        {options.map((o) => (
          <button
            key={o}
            type="button"
            className={`${cls}${value === o ? ' on' : ''}`}
            aria-pressed={value === o}
            disabled={disabled}
            onClick={() => onChange(value === o ? '' : o)}
          >
            {o}
          </button>
        ))}
      </div>
    </div>
  )
}

export function TriRow({
  label,
  options,
  value,
  onChange,
  risk = false,
  disabled = false,
}: {
  label: string
  options: string[]
  value: string
  onChange: (v: string) => void
  risk?: boolean
  disabled?: boolean
}) {
  return (
    <div className="row">
      <div className="t">{label.replace(/\//g, ' / ')}</div>
      <div style={{ display: 'flex', gap: 4, flex: 'none' }} role="radiogroup" aria-label={label}>
        {options.map((o) => (
          <button
            key={o}
            type="button"
            className={`tri${value === o ? ' on' + (risk && o === 'Yes' ? ' risk' : '') : ''}`}
            aria-pressed={value === o}
            disabled={disabled}
            onClick={() => onChange(value === o ? '' : o)}
          >
            {o}
          </button>
        ))}
      </div>
    </div>
  )
}

export function TextField({
  id,
  label,
  value,
  onChange,
  placeholder,
  type = 'text',
  inputMode,
  after,
}: {
  id: string
  label: ReactNode
  value: string
  onChange: (v: string) => void
  placeholder?: string
  type?: string
  inputMode?: 'text' | 'tel' | 'numeric' | 'decimal'
  after?: ReactNode
}) {
  const input = (
    <input autoComplete="off"
      className="fld"
      id={id}
      type={type}
      inputMode={inputMode}
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      style={after ? { flex: 1, minWidth: 0 } : undefined}
    />
  )
  return (
    <div>
      <label className="lbl" htmlFor={id}>
        {label}
      </label>
      {after ? (
        <div style={{ display: 'flex', gap: 8 }}>
          {input}
          {after}
        </div>
      ) : (
        input
      )}
    </div>
  )
}

// ₹ amount box: type the full amount in rupees; commas are added as you type (12,34,567).
export function MoneyField({
  id,
  label,
  value,
  onChange,
  unit = '',
  placeholder = '0',
  disabled = false,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  unit?: string
  placeholder?: string
  disabled?: boolean
}) {
  return (
    <div>
      <label className="lbl" htmlFor={id}>
        {label}
      </label>
      <MoneyBox id={id} value={value} onChange={onChange} unit={unit} placeholder={placeholder} disabled={disabled} />
    </div>
  )
}

export function MoneyBox({
  id,
  value,
  onChange,
  unit = '',
  placeholder = '0',
  style,
  disabled = false,
}: {
  id: string
  value: string
  onChange: (v: string) => void
  unit?: string
  placeholder?: string
  style?: React.CSSProperties
  disabled?: boolean
}) {
  return (
    <div className="box" style={{ ...style, ...(disabled ? { opacity: 0.4, pointerEvents: 'none' } : null) }}>
      <span style={{ color: 'var(--muted)' }}>₹</span>
      <input autoComplete="off"
        className="mono"
        id={id}
        disabled={disabled}
        inputMode="numeric"
        placeholder={placeholder}
        value={formatINR(value)}
        onChange={(e) => onChange(e.target.value.replace(/[^\d]/g, '').slice(0, 13))}
      />
      {unit && <span className="unit">{unit}</span>}
    </div>
  )
}

export function cleanNumber(raw: string): string {
  const digits = raw.replace(/[^\d.]/g, '')
  const [whole, ...rest] = digits.split('.')
  return rest.length ? `${whole}.${rest.join('')}` : whole
}

// A mobile number is exactly 10 digits. Anything else typed or pasted is dropped; a pasted "+91 98765 43210"
// or "098765 43210" keeps its last 10 digits.
export function cleanMobile(raw: string): string {
  let digits = raw.replace(/\D/g, '')
  if (digits.length > 10) digits = digits.replace(/^(91|0)/, '')
  return digits.slice(0, 10)
}

// A mobile number box: fixed +91 in front, 10 digits only.
export function MobileField({
  id,
  label,
  value,
  onChange,
}: {
  id: string
  label: ReactNode
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div>
      <label className="lbl" htmlFor={id}>
        {label}
      </label>
      <div className="box mobile-box">
        <span className="mono" style={{ fontSize: 14, color: 'var(--muted)' }}>
          +91
        </span>
        <input
          autoComplete="off"
          id={id}
          type="tel"
          inputMode="numeric"
          maxLength={10}
          style={{ fontWeight: 500 }}
          value={value}
          onChange={(e) => onChange(cleanMobile(e.target.value))}
        />
      </div>
    </div>
  )
}

// Our own dropdown list: a field that opens a short scrollable list of options (about five rows tall).
// Used instead of the phone's plain pop-up list so long options (for example the loan purposes) stay readable.
function DropdownList({
  label,
  options,
  value,
  onChange,
  disabled,
}: {
  label: string
  options: string[]
  value: string
  onChange: (v: string) => void
  disabled: boolean
}) {
  const id = useId()
  const box = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [up, setUp] = useState(false) // open upwards when there is no room below

  useEffect(() => {
    if (!open) return
    const outside = (e: PointerEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false)
    }
    const escape = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  function toggle() {
    if (disabled) return
    if (!open && box.current) {
      // Room below the field, inside the scrolling page, for a list of about 5 rows (~270px)?
      const scroller = box.current.closest('.scroll')
      const below = (scroller?.getBoundingClientRect().bottom ?? window.innerHeight) - box.current.getBoundingClientRect().bottom
      const above = box.current.getBoundingClientRect().top - (scroller?.getBoundingClientRect().top ?? 0)
      setUp(below < 270 && above > below)
    }
    setOpen((o) => !o)
  }

  return (
    <div ref={box} className="dd">
      <label className="lbl" htmlFor={id}>
        {label}
      </label>
      <button
        id={id}
        type="button"
        className="fld dd-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={toggle}
      >
        <span className={value ? undefined : 'dd-ph'}>{value || 'Select…'}</span>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d={open ? 'M6 15l6-6 6 6' : 'M6 9l6 6 6-6'} />
        </svg>
      </button>
      {open && (
        <div className={`dd-panel${up ? ' up' : ''}`} role="listbox" aria-label={label}>
          <button type="button" role="option" aria-selected={!value} className="dd-item dd-ph" onClick={() => { onChange(''); setOpen(false) }}>
            Select…
          </button>
          {options.map((o) => (
            <button
              key={o}
              type="button"
              role="option"
              aria-selected={value === o}
              className={`dd-item${value === o ? ' sel' : ''}`}
              onClick={() => {
                onChange(o)
                setOpen(false)
              }}
            >
              {o}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
