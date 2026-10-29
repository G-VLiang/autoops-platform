import { useState } from 'react'
import { Card, Form, Input, Button, Typography, message } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { login } from '../api/modules'

export default function Login() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const onFinish = async (values) => {
    setLoading(true)
    try {
      const { data } = await login(values.username, values.password)
      localStorage.setItem('token', data.access_token)
      localStorage.setItem('username', values.username)
      message.success('登录成功')
      navigate('/')
    } catch (e) {
      message.error(e.response?.data?.detail || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(135deg,#1677ff 0%,#69b1ff 100%)' }}>
      <Card style={{ width: 380, boxShadow: '0 8px 24px rgba(0,0,0,0.15)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Typography.Title level={3} style={{ marginBottom: 4 }}>⚙️ AutoOps</Typography.Title>
          <Typography.Text type="secondary">运维自动化平台</Typography.Text>
        </div>
        <Form onFinish={onFinish} initialValues={{ username: 'admin', password: 'admin123' }}>
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" size="large" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" size="large" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block size="large" loading={loading}>
              登录
            </Button>
          </Form.Item>
        </Form>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          默认账号 admin / admin123
        </Typography.Text>
      </Card>
    </div>
  )
}
