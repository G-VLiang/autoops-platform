import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider, App as AntApp } from 'antd'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Hosts from './pages/Hosts'
import Tasks from './pages/Tasks'
import Inspections from './pages/Inspections'
import InspectionPlans from './pages/InspectionPlans'
import Security from './pages/Security'

function RequireAuth({ children }) {
  const token = localStorage.getItem('token')
  if (!token) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  return (
    <ConfigProvider>
      <AntApp>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/"
              element={
                <RequireAuth>
                  <Layout />
                </RequireAuth>
              }
            >
              <Route index element={<Dashboard />} />
              <Route path="hosts" element={<Hosts />} />
              <Route path="tasks" element={<Tasks />} />
              <Route path="inspections" element={<Inspections />} />
              <Route path="plans" element={<InspectionPlans />} />
              <Route path="security" element={<Security />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  )
}
