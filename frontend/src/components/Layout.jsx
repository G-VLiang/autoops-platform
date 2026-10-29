import { Layout as AntLayout, Menu, Dropdown, Space, Avatar } from 'antd'
import {
  DashboardOutlined, CloudServerOutlined, ThunderboltOutlined,
  AuditOutlined, ScheduleOutlined, SafetyOutlined, UserOutlined, LogoutOutlined,
} from '@ant-design/icons'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'

const { Header, Sider, Content } = AntLayout

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '总览看板' },
  { key: '/hosts', icon: <CloudServerOutlined />, label: '资产管理' },
  { key: '/tasks', icon: <ThunderboltOutlined />, label: '作业中心' },
  { key: '/inspections', icon: <AuditOutlined />, label: '巡检中心' },
  { key: '/plans', icon: <ScheduleOutlined />, label: '巡检计划' },
  { key: '/security', icon: <SafetyOutlined />, label: '安全审计' },
]

export default function Layout() {
  const navigate = useNavigate()
  const location = useLocation()
  const username = localStorage.getItem('username') || 'admin'

  const selectedKey = '/' + (location.pathname.split('/')[1] || '')

  const logout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    navigate('/login')
  }

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider theme="dark" width={200}>
        <div style={{ height: 56, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 600, fontSize: 16 }}>
          ⚙️ AutoOps
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={(e) => navigate(e.key)}
        />
      </Sider>
      <AntLayout>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
          <Dropdown
            menu={{
              items: [{ key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: logout }],
            }}
          >
            <Space style={{ cursor: 'pointer' }}>
              <Avatar size="small" icon={<UserOutlined />} />
              <span>{username}</span>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ margin: 24 }}>
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  )
}
