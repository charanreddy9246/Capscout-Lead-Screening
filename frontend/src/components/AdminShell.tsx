// The top of every Admin / Super Admin screen: the logo, who is signed in, sign out.

import type { ReactNode } from 'react'
import { useAuth } from '../auth'
import { ROLE } from '../pages/Home'
import { Logo } from './Logo'
import { IconPower } from './icons'

export default function AdminShell({ children }: { children: ReactNode }) {
  const { staff, logout } = useAuth()

  return (
    <>
      <div className="hdr shell-hdr" style={{ padding: '14px 18px 12px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Logo />
          <button
            className="icon-btn"
            style={{ width: 36, height: 36, color: 'var(--muted)' }}
            aria-label="Sign out"
            onClick={() => confirm('Sign out?') && logout()}
          >
            <IconPower />
          </button>
        </div>
        <div className="hdr-sub">
          {staff?.full_name} · {ROLE[staff?.role ?? ''] ?? ''}
        </div>
      </div>
      {children}
    </>
  )
}
