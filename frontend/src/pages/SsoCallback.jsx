import { useEffect, useState } from 'react'
import { Result, Spin } from 'antd'
import { useNavigate } from 'react-router-dom'
import { getMe } from '../api/modules'
import { saveMe, saveSession } from '../api/session'

/** SSO 回调落地点：从 URL fragment 取 token（不经过服务端日志），换用户信息后进首页。 */
export default function SsoCallback() {
  const navigate = useNavigate()
  const [error, setError] = useState('')

  useEffect(() => {
    const hash = window.location.hash.replace(/^#/, '')
    const params = new URLSearchParams(hash)
    const token = params.get('token')
    const err = params.get('error')
    if (err) {
      setError(decodeURIComponent(err))
      return
    }
    if (!token) {
      setError('未获取到登录凭证')
      return
    }
    saveSession({ access_token: token })
    // 清掉地址栏里的 token，避免被复制/回放
    window.history.replaceState(null, '', '/sso/callback')
    getMe()
      .then((r) => {
        saveMe(r.data)
        navigate('/', { replace: true })
      })
      .catch(() => setError('登录凭证无效或已过期'))
  }, [navigate])

  if (!error) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin size="large" tip="正在完成单点登录…"><div style={{ padding: 40 }} /></Spin>
      </div>
    )
  }

  return (
    <Result status="error" title="单点登录失败" subTitle={error}
      extra={<a onClick={() => navigate('/login', { replace: true })}>返回登录页</a>} />
  )
}
