import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { ConfigProvider, App as AntApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import Layout from './components/Layout'
import ErrorBoundary from './components/ErrorBoundary'
import Login from './pages/Login'
import SsoCallback from './pages/SsoCallback'
import Dashboard from './pages/Dashboard'
import Hosts from './pages/Hosts'
import Tasks from './pages/Tasks'
import Inspections from './pages/Inspections'
import InspectionPlans from './pages/InspectionPlans'
import Alerts from './pages/Alerts'
import Security from './pages/Security'
import Tenants from './pages/Tenants'
import NotFound from './pages/NotFound'
import { isLoggedIn } from './api/session'

function RequireAuth({ children }) {
  const location = useLocation()
  if (!isLoggedIn()) {
    const redirect = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?redirect=${redirect}`} replace />
  }
  return children
}

export default function App() {
  return (
    <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#1677ff', borderRadius: 8 } }}>
      <AntApp>
        <ErrorBoundary>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/sso/callback" element={<SsoCallback />} />
              <Route
                path="/"
                element={
                  <RequireAuth>
                    <Layout />
                  </RequireAuth>
                }
              >
                <Route index element={<ErrorBoundary><Dashboard /></ErrorBoundary>} />
                <Route path="hosts" element={<ErrorBoundary><Hosts /></ErrorBoundary>} />
                <Route path="tasks" element={<ErrorBoundary><Tasks /></ErrorBoundary>} />
                <Route path="inspections" element={<ErrorBoundary><Inspections /></ErrorBoundary>} />
                <Route path="plans" element={<ErrorBoundary><InspectionPlans /></ErrorBoundary>} />
                <Route path="alerts" element={<ErrorBoundary><Alerts /></ErrorBoundary>} />
                <Route path="security" element={<ErrorBoundary><Security /></ErrorBoundary>} />
                <Route path="tenants" element={<ErrorBoundary><Tenants /></ErrorBoundary>} />
                <Route path="*" element={<NotFound />} />
              </Route>
              <Route path="*" element={<NotFound />} />
            </Routes>
          </BrowserRouter>
        </ErrorBoundary>
      </AntApp>
    </ConfigProvider>
  )
}
