import { useEffect, useState } from 'react'
import { App, Alert, Button, Card, Divider, Form, Input, Space, Tag, Typography } from 'antd'
import { LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { getProviders, login } from '../api/modules'
import { saveSession } from '../api/session'

const { Title, Text } = Typography

export default function Login() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [providers, setProviders] = useState({ local: true, ldap: false, oidc: false })

  useEffect(() => {
    getProviders().then((r) => setProviders(r.data)).catch(() => {})
  }, [])

  const onFinish = async (values) => {
    setLoading(true)
    try {
      const r = await login(values.username, values.password)
      saveSession(r.data)
      message.success(`欢迎回来，${r.data.display_name || r.data.username}`)
      navigate('/', { replace: true })
    } catch (e) {
      message.error(e?.response?.data?.detail || '登录失败，请检查账号密码')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #f0f5ff 0%, #e6f4ff 45%, #f6ffed 100%)',
    }}>
      <Card style={{ width: 400, boxShadow: '0 12px 40px rgba(22,119,255,0.12)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={3} style={{ marginBottom: 4 }}>AutoOps 运维自动化平台</Title>
          <Text type="secondary">资产 · 作业 · 巡检 · 告警 一体化</Text>
        </div>

        <Form layout="vertical" onFinish={onFinish} initialValues={{ username: '' }} requiredMark={false}>
          <Form.Item name="username" label="账号" rules={[{ required: true, message: '请输入账号' }]}>
            <Input size="large" prefix={<UserOutlined />} placeholder="用户名 / 域账号" autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password size="large" prefix={<LockOutlined />} placeholder="密码"
              autoComplete="current-password" onPressEnter={() => {}} />
          </Form.Item>
          <Button type="primary" htmlType="submit" size="large" block loading={loading}>
            登录
          </Button>
        </Form>

        {providers.oidc && (
          <>
            <Divider plain style={{ color: '#bbb', fontSize: 12 }}>或</Divider>
            <Button size="large" block icon={<SafetyCertificateOutlined />}
              onClick={() => { window.location.href = '/api/v1/auth/oidc/login' }}>
              企业 SSO 登录
            </Button>
          </>
        )}

        <Space size={4} style={{ marginTop: 16, width: '100%', justifyContent: 'center' }}>
          {providers.ldap && <Tag color="blue">支持 LDAP 域账号</Tag>}
          {providers.oidc && <Tag color="purple">OIDC 单点登录</Tag>}
        </Space>

        <Alert style={{ marginTop: 16 }} type="info" showIcon
          message="初始账号 admin / admin123"
          description="首次部署后请立即修改密码（backend/scripts/set_admin_password.py）。"
        />
      </Card>
    </div>
  )
}
