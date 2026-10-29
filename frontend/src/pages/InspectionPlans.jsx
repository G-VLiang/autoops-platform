import { useEffect, useState } from 'react'
import { Card, Table, Button, Modal, Form, Input, Select, Tag, Space, Popconfirm, message, Tabs, Switch, Drawer, Descriptions, Empty } from 'antd'
import { PlusOutlined, PlayCircleOutlined, BellOutlined, FileTextOutlined } from '@ant-design/icons'
import {
  listPlans, createPlan, updatePlan, deletePlan, runPlan,
  listTemplates, listGroups, listHosts,
  listReports, listAlerts, createAlert, deleteAlert, testAlert,
} from '../api/modules'

const statusColor = { success: 'green', failed: 'red', partial: 'orange' }
const cronOptions = [
  { label: '每天 02:00', value: 'daily' },
  { label: '每小时', value: 'hourly' },
  { label: '每 30 分钟', value: 'every30min' },
]

export default function InspectionPlans() {
  const [plans, setPlans] = useState([])
  const [templates, setTemplates] = useState([])
  const [groups, setGroups] = useState([])
  const [hosts, setHosts] = useState([])
  const [reports, setReports] = useState([])
  const [alerts, setAlerts] = useState([])
  const [planModal, setPlanModal] = useState(false)
  const [alertModal, setAlertModal] = useState(false)
  const [reportDrawer, setReportDrawer] = useState(false)
  const [form] = Form.useForm()
  const [alertForm] = Form.useForm()

  const load = () => {
    listPlans().then((r) => setPlans(r.data)).catch(() => {})
    listTemplates().then((r) => setTemplates(r.data)).catch(() => {})
    listGroups().then((r) => setGroups(r.data)).catch(() => {})
    listHosts().then((r) => setHosts(r.data)).catch(() => {})
    listReports().then((r) => setReports(r.data)).catch(() => {})
    listAlerts().then((r) => setAlerts(r.data)).catch(() => {})
  }

  useEffect(load, [])

  const submitPlan = async () => {
    const values = await form.validateFields()
    await createPlan(values)
    message.success('计划已创建')
    setPlanModal(false)
    form.resetFields()
    load()
  }

  const doRun = async (plan) => {
    await runPlan(plan.id)
    message.success('巡检已执行')
    load()
  }

  const toggleEnabled = async (plan, checked) => {
    await updatePlan(plan.id, { name: plan.name, template_id: plan.template_id, target_type: plan.target_type, target_id: plan.target_id, cron: plan.cron, enabled: checked })
    load()
  }

  const submitAlert = async () => {
    const values = await alertForm.validateFields()
    await createAlert(values)
    message.success('告警配置已保存')
    setAlertModal(false)
    alertForm.resetFields()
    load()
  }

  const planColumns = [
    { title: '名称', dataIndex: 'name' },
    { title: '巡检模板', dataIndex: 'template_name', render: (v) => v || '-' },
    { title: '调度', dataIndex: 'cron', render: (v) => <Tag color="blue">{v}</Tag> },
    { title: '启用', dataIndex: 'enabled', render: (v, r) => <Switch size="small" checked={v} onChange={(c) => toggleEnabled(r, c)} /> },
    { title: '上次执行', dataIndex: 'last_run_at', render: (v) => v ? new Date(v).toLocaleString() : '-' },
    {
      title: '操作', render: (_, r) => (
        <Space>
          <Button type="link" size="small" icon={<PlayCircleOutlined />} onClick={() => doRun(r)}>立即执行</Button>
          <Popconfirm title="确定删除？" onConfirm={async () => { await deletePlan(r.id); load() }}>
            <Button type="link" danger size="small">删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const reportColumns = [
    { title: '计划', dataIndex: 'plan_name' },
    { title: '模板', dataIndex: 'template_name' },
    { title: '状态', dataIndex: 'status', render: (v) => <Tag color={statusColor[v]}>{v}</Tag> },
    { title: '结果', dataIndex: 'summary', render: (s) => <Space size={4}>{Object.entries(s || {}).map(([k, v]) => <Tag key={k}>{k}:{v}</Tag>)}</Space> },
    { title: '时间', dataIndex: 'created_at', render: (v) => new Date(v).toLocaleString() },
  ]

  const alertColumns = [
    { title: '名称', dataIndex: 'name' },
    { title: '渠道', dataIndex: 'channel', render: (v) => <Tag color="geekblue">{v}</Tag> },
    { title: 'Webhook', dataIndex: 'webhook_url', render: (v) => v || <span style={{ color: '#999' }}>未配置</span> },
    { title: '启用', dataIndex: 'enabled', render: (v) => v ? <Tag color="green">是</Tag> : <Tag>否</Tag> },
    {
      title: '操作', render: (_, r) => (
        <Space>
          <Button type="link" size="small" onClick={async () => { await testAlert(r.id); message.info('测试已发送（未配 webhook 则仅记录日志）') }}>测试</Button>
          <Popconfirm title="确定删除？" onConfirm={async () => { await deleteAlert(r.id); load() }}>
            <Button type="link" danger size="small">删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Card
        title="巡检计划"
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setPlanModal(true)}>新建计划</Button>}
      >
        <Tabs
          items={[
            {
              key: 'plans', label: '巡检计划',
              children: <Table rowKey="id" dataSource={plans} columns={planColumns} />,
            },
            {
              key: 'reports', label: <span><FileTextOutlined /> 巡检报告</span>,
              children: <Table rowKey="id" dataSource={reports} columns={reportColumns} />,
            },
            {
              key: 'alerts', label: <span><BellOutlined /> 告警配置</span>,
              children: (
                <div>
                  <Button icon={<PlusOutlined />} onClick={() => setAlertModal(true)} style={{ marginBottom: 12 }}>添加告警</Button>
                  <Table rowKey="id" dataSource={alerts} columns={alertColumns} />
                </div>
              ),
            },
          ]}
        />
      </Card>

      {/* 新建计划 */}
      <Modal title="新建巡检计划" open={planModal} onOk={submitPlan} onCancel={() => setPlanModal(false)}>
        <Form form={form} layout="vertical" initialValues={{ target_type: 'group', cron: 'daily', enabled: true }}>
          <Form.Item name="name" label="计划名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="template_id" label="巡检模板" rules={[{ required: true }]}>
            <Select options={templates.map((t) => ({ label: t.name, value: t.id }))} />
          </Form.Item>
          <Form.Item name="target_type" label="目标类型">
            <Select options={[{ label: '主机组', value: 'group' }, { label: '单台主机', value: 'host' }]} />
          </Form.Item>
          <Form.Item name="target_id" label="目标" rules={[{ required: true }]}>
            <Select
              options={[
                ...groups.map((g) => ({ label: `[组] ${g.name}`, value: g.id })),
                ...hosts.map((h) => ({ label: `[主机] ${h.hostname}`, value: h.id })),
              ]}
            />
          </Form.Item>
          <Form.Item name="cron" label="调度周期">
            <Select options={cronOptions} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* 添加告警 */}
      <Modal title="添加告警配置" open={alertModal} onOk={submitAlert} onCancel={() => setAlertModal(false)}>
        <Form form={alertForm} layout="vertical" initialValues={{ channel: 'webhook', enabled: true }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="channel" label="渠道">
            <Select options={[
              { label: '通用 Webhook', value: 'webhook' },
              { label: '钉钉机器人', value: 'dingtalk' },
              { label: '企业微信机器人', value: 'wecom' },
            ]} />
          </Form.Item>
          <Form.Item name="webhook_url" label="Webhook 地址"><Input placeholder="https://oapi.dingtalk.com/robot/send?access_token=..." /></Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked"><Switch /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
