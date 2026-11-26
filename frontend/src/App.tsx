import MeetingType from './pages/MeetingType'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth'
import ConvertPage from './pages/ConvertPage'
import CustomerPage from './pages/CustomerPage'
import Dashboard from './pages/Dashboard'
import Home from './pages/Home'
import Login from './pages/Login'
import NoAccess from './pages/NoAccess'
import MeetingPage from './pages/MeetingPage'
import SetPassword from './pages/SetPassword'
import TabBar from './components/TabBar'
import Users from './pages/Users'

function Routed() {
  return (
    <>
      <Pages />
      <TabBar />
    </>
  )
}

function Pages() {
  const { staff, loading } = useAuth()
  const { pathname } = useLocation()
  if (pathname === '/set-password') return <SetPassword /> // the link itself is the proof: no sign-in needed
  if (loading) return <div className="splash">Loading…</div>
  if (!staff) return <Login />

  // One app, one login. What opens first, and what is reachable, depends on the role.
  if (staff.role === 'ADMIN' || staff.role === 'SUPER_ADMIN') // the Super Admin sees the same as an Admin
    return (
      <>
        <Routes>
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="dashboard/:staffId" element={<Dashboard />} />
          <Route path="users" element={<Users />} />
          <Route path="customers/:id" element={<CustomerPage />} />
          <Route path="customers" element={<Home />} />
          <Route path="new-meeting" element={<MeetingType />} />
          <Route path="new-meeting/:kind" element={<MeetingType />} />
          <Route path="new" element={<MeetingPage key="new" />} />
          <Route path="customers/:id/convert" element={<ConvertPage />} />
          <Route path="customers/:id/meeting" element={<MeetingPage />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </>
    )

  return (
    <>
    <Routes>
      <Route index element={<Home />} />
      <Route path="dashboard" element={<Dashboard />} />
      <Route path="users" element={<NoAccess />} />
      <Route path="new-meeting" element={<MeetingType />} />
      <Route path="new-meeting/:kind" element={<MeetingType />} />
      <Route path="new" element={<MeetingPage key="new" />} />
      <Route path="customers/:id" element={<CustomerPage />} />
      <Route path="customers/:id/convert" element={<ConvertPage />} />
      <Route path="customers/:id/meeting" element={<MeetingPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="app">
          <Routed />
        </div>
      </BrowserRouter>
    </AuthProvider>
  )
}
