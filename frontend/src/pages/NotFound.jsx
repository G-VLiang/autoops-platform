import { Button, Result } from 'antd'
import { useNavigate } from 'react-router-dom'

export default function NotFound() {
  const navigate = useNavigate()
  return (
    <Result
      status="404"
      title="404"
      subTitle="页面不存在，可能是链接已失效或地址输错了。"
      extra={<Button type="primary" onClick={() => navigate('/', { replace: true })}>回到看板</Button>}
    />
  )
}
