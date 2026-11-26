// Shown when someone opens a page their role cannot use (a typed address, an old bookmark).
// The server refuses the data anyway; this screen just says so clearly.

import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

export default function NoAccess() {
  const navigate = useNavigate()
  const { staff } = useAuth()
  const home = staff?.role === 'SM' ? '/' : '/dashboard'
  return (
    <div className="scroll" style={{ justifyContent: 'center', alignItems: 'center', textAlign: 'center', gap: 16 }}>
      <div className="page-title">You don't have access to this page</div>
      <div className="muted" style={{ fontSize: 14, maxWidth: 280 }}>
        Your account can't open this section. If you think it should, ask your admin.
      </div>
      <button className="btn primary" style={{ padding: '0 28px', marginTop: 8 }} onClick={() => navigate(home, { replace: true })}>
        Go to my home screen
      </button>
    </div>
  )
}
