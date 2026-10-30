import { useEffect, useState } from 'react'
import { Layout as AntLayout, Avatar, Badge, Dropdown, Menu, Space, Tag } from 'antd'
import {
  AlertOutlined, ApartmentOutlined, AuditOutlined, CloudServerOutlined, DashboardOutlined,
  LogoutOutlined, SafetyOutlined, ScheduleOutlined, ThunderboltOutlined, UserOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { getAlertSummary, getMe } from '../api/modules'
import {
  clearSession, getAuthSource, getDisplayName, getRole, getTenantName, isSuper, saveMe,
} from '../api/session'

const { Header, Sider, Content } = AntLayout

const ROLE_LABEL = {
  superadmin: { text: '平台超管', color: 'magenta' },
  admin: { text: '管理员', color: 'blue' },
  operator: { text: '运维', color: 'green' },
  viewer: { text: '只读', color: 'default' },
}

export default function Layout() {
  const navigate = useNavigate()
  const location = useLocation()
  const [me, setMe] = useState({
    name: getDisplayName(), role: getRole(), tenant: getTenantName(), super: isSuper(),
  })
  const [activeAlerts, setActiveAlerts] = useState(0)

  useEffect(() => {
    getMe()
      .then((r) => {
        saveMe(r.data)
        setMe({
          name: r.data.display_name || r.data.username,
          role: r.data.role,
          tenant: r.data.tenant_name,
          super: r.data.is_super,
        })
      })
      .catch(() => {})
  }, [])

  // 活跃告警数：轻量轮询，让值班人员随时看到有没有未处理告警
  useEffect(() => {
    let alive = true
    const pull = () => {
      getAlertSummary()
        .then((r) => { if (alive) setActiveAlerts(r.data?.active || 0) })
        .catch(() => {})
    }
    pull()
    const timer = setInterval(pull, 60000)
    return () => { alive = false; clearInterval(timer) }
  }, [])

  const menuItems = [
    { key: '/', icon: <DashboardOutlined />, label: '总览看板' },
    { key: '/hosts', icon: <CloudServerOutlined />, label: '资产管理' },
    { key: '/tasks', icon: <ThunderboltOutlined />, label: '作业中心' },
    { key: '/inspections', icon: <AuditOutlined />, label: '巡检中心' },
    { key: '/plans', icon: <ScheduleOutlined />, label: '巡检计划' },
    {
      key: '/alerts', icon: <AlertOutlined />,
      label: (
        <span>
          告警中心
          {activeAlerts > 0 && (
            <Badge count={activeAlerts} size="small" style={{ marginLeft: 6 }} />
          )}
        </span>
      ),
    },
    { key: '/security', icon: <SafetyOutlined />, label: '安全审计' },
  ]
  if (me.super) {
    menuItems.push({ key: '/tenants', icon: <ApartmentOutlined />, label: '租户管理' })
  }

  const selectedKey = '/' + (location.pathname.split('/')[1] || '')
  const role = ROLE_LABEL[me.role] || { text: me.role || '-', color: 'default' }

  const logout = () => {
    clearSession()
    navigate('/login', { replace: true })
  }

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider theme="dark" width={208} breakpoint="lg" collapsedWidth={64}>
        <div style={{
          height: 56, display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontWeight: 600, fontSize: 16, letterSpacing: 0.5,
        }}>
          ⚙️ AutoOps
        </div>
        <Menu
          theme="dark" mode="inline" selectedKeys={[selectedKey]}
          items={menuItems} onClick={(e) => navigate(e.key)}
        />
      </Sider>
      <AntLayout>
        <Header style={{
          background: '#fff', padding: '0 20px', display: 'flex',
          justifyContent: 'space-between', alignItems: 'center',
          boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
        }}>
          <Space size={6}>
            {me.tenant && <Tag color="geekblue" bordered={false}>{me.tenant}</Tag>}
            <Tag color={role.color} bordered={false}>{role.text}</Tag>
            {getAuthSource() !== 'local' && (
              <Tag bordered={false} color="purple">{getAuthSource().toUpperCase()}</Tag>
            )}
          </Space>
          <Dropdown
            menu={{ items: [{ key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: logout }] }}
          >
            <Space style={{ cursor: 'pointer' }}>
              <Avatar size="small" style={{ background: '#1677ff' }} icon={<UserOutlined />} />
              <span>{me.name}</span>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ margin: 20 }}>
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  )
}
