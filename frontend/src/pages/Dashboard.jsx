import { useEffect, useState } from 'react'
import { Row, Col, Card, Statistic, Table, Tag, Space, Progress } from 'antd'
import { CloudServerOutlined, ThunderboltOutlined, AuditOutlined, CheckCircleOutlined, ScheduleOutlined } from '@ant-design/icons'
import { listHosts, listTasks, listTemplates, listPlans, listReports } from '../api/modules'

const statusColor = {
  success: 'green', failed: 'red', partial: 'orange', running: 'blue', pending: 'default',
}

export default function Dashboard() {
  const [hosts, setHosts] = useState([])
  const [tasks, setTasks] = useState([])
  const [templates, setTemplates] = useState([])
  const [plans, setPlans] = useState([])
  const [reports, setReports] = useState([])

  useEffect(() => {
    listHosts().then((r) => setHosts(r.data)).catch(() => {})
    listTasks().then((r) => setTasks(r.data)).catch(() => {})
    listTemplates().then((r) => setTemplates(r.data)).catch(() => {})
    listPlans().then((r) => setPlans(r.data)).catch(() => {})
    listReports().then((r) => setReports(r.data)).catch(() => {})
  }, [])

  const successCount = tasks.filter((t) => t.status === 'success').length
  const successRate = tasks.length ? Math.round((successCount / tasks.length) * 100) : 0

  const reportOk = reports.filter((r) => r.status === 'success').length
  const reportRate = reports.length ? Math.round((reportOk / reports.length) * 100) : 100

  const recentTasks = tasks.slice(0, 5)
  const recentReports = reports.slice(0, 5)

  return (
    <div>
      <Row gutter={16}>
        <Col span={4}>
          <Card><Statistic title="主机总数" value={hosts.length} prefix={<CloudServerOutlined />} /></Card>
        </Col>
        <Col span={4}>
          <Card><Statistic title="任务总数" value={tasks.length} prefix={<ThunderboltOutlined />} /></Card>
        </Col>
        <Col span={4}>
          <Card><Statistic title="巡检模板" value={templates.length} prefix={<AuditOutlined />} /></Card>
        </Col>
        <Col span={4}>
          <Card><Statistic title="巡检计划" value={plans.length} prefix={<ScheduleOutlined />} /></Card>
        </Col>
        <Col span={4}>
          <Card><Statistic title="任务成功率" value={successRate} suffix="%" prefix={<CheckCircleOutlined />} /></Card>
        </Col>
        <Col span={4}>
          <Card title="巡检健康度"><Progress percent={reportRate} size="small" /></Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card title="最近任务" size="small">
            <Table
              rowKey="id"
              dataSource={recentTasks}
              pagination={false}
              size="small"
              columns={[
                { title: '名称', dataIndex: 'name' },
                { title: '类型', dataIndex: 'task_type', render: (v) => <Tag>{v}</Tag> },
                { title: '状态', dataIndex: 'status', render: (v) => <Tag color={statusColor[v]}>{v}</Tag> },
                { title: '结果', dataIndex: 'summary', render: (s) => s ? <Space size={4}>{Object.entries(s).map(([k, val]) => <Tag key={k}>{k}:{val}</Tag>)}</Space> : '-' },
              ]}
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="最近巡检报告" size="small">
            <Table
              rowKey="id"
              dataSource={recentReports}
              pagination={false}
              size="small"
              columns={[
                { title: '计划', dataIndex: 'plan_name' },
                { title: '状态', dataIndex: 'status', render: (v) => <Tag color={statusColor[v]}>{v}</Tag> },
                { title: '结果', dataIndex: 'summary', render: (s) => s ? <Space size={4}>{Object.entries(s).map(([k, val]) => <Tag key={k}>{k}:{val}</Tag>)}</Space> : '-' },
                { title: '时间', dataIndex: 'created_at', render: (v) => new Date(v).toLocaleString() },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  )
}
