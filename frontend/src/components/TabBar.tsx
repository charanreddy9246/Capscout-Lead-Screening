// The same three tabs for every role. A tab your role cannot use opens "access denied".

import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

export default function TabBar() {
  const { staff } = useAuth()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  if (!staff) return null
  // full-screen flows keep their own buttons
  if (/^\/(new|new-meeting|set-password)/.test(pathname) || /^\/customers\/.+/.test(pathname)) return null

  const tabs = [
    { label: 'Customers', to: staff.role === 'SM' ? '/' : '/customers', on: pathname === '/' || pathname === '/customers' },
    { label: 'Dashboard', to: '/dashboard', on: pathname.startsWith('/dashboard') },
    { label: 'Users', to: '/users', on: pathname.startsWith('/users') },
  ]
  return (
    <nav className="tabbar" aria-label="Main menu">
      {tabs.map((t) => (
        <button key={t.to} type="button" className={t.on ? 'on' : ''} aria-current={t.on ? 'page' : undefined} onClick={() => navigate(t.to)}>
          {t.label}
        </button>
      ))}
    </nav>
  )
}
