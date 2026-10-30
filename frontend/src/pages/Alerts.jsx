import { useEffect, useState } from 'react'
import {
  Alert, Badge, Button, Card, Descriptions, Form, Input, InputNumber, Modal, Popconfirm,
  Select, Space, Statistic, Switch, Table, Tabs, Tag, Tooltip, message,
} from 'antd'
import {
  BellOutlined, CheckCircleOutlined, MutedOutlined, PlusOutlined, ReloadOutlined,
  SendOutlined,
} from '@ant-design/icons'
import {
  createAlertConfig, createSilence, deleteAlertConfig, deleteSilence, getAlertSummary,
  listAlertConfigs, listAlertEvents, listPlans, listSilences, resolveAlertEvent, testAlertConfig,
  updateAlertConfig,
} from '../api/modules'

const SEVERITY = {
  critical: { label: '严重', color: 'red' },
  warning: { label: '警告', color: 'orange' },
  info: { label: '提示', color: 'blue' },
}
const CHANNELS = [
  { label: '通用 Webhook', value: 'webhook' },
  { label: '钉钉机器人', value: 'dingtalk' },
  { label: '企业微信机器人', value: 'wecom' },
]
const fmt = (v) => (v ? new Date(v).toLocaleString() : '-')

export default function Alerts() {
  const [events, setEvents] = useState([])
  const [configs, setConfigs] = useState([])
  const [silences, setSilences] = useState([])
  const [plans, setPlans] = useState([])
  const [summary, setSummary] = useState(null)
  const [statusFilter, setStatusFilter] = useState('firing')
  const [cfgModal, setCfgModal] = useState(null)   // null | {} | 现有配置
  const [silenceModal, setSilenceModal] = useState(false)
  const [loading, setLoading] = useState(false)
  const [cfgForm] = Form.useForm()
  const [silenceForm] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const params = statusFilter === 'all' ? {} : { status: statusFilter }
      const [e, c, s, sm, p] = await Promise.all([
        listAlertEvents(params), listAlertConfigs(), listSilences(),
        getAlertSummary(), listPlans(),
      ])
      setEvents(e.data); setConfigs(c.data); setSilences(s.data)
      setSummary(sm.data); setPlans(p.data)
    } catch (err) {
      message.error(err?.response?.data?.detail || '加载告警数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [statusFilter])

  const openConfig = (cfg) => {
    setCfgModal(cfg || {})
    setTimeout(() => cfgForm.setFieldsValue(cfg || {
      channel: 'webhook', enabled: true, min_severity: 'info', repeat_interval_minutes: 0,
    }), 0)
  }

  const submitConfig = async () => {
    const values = await cfgForm.validateFields()
    try {
      if (cfgModal?.id) await updateAlertConfig(cfgModal.id, values)
      else await createAlertConfig(values)
      message.success('通知渠道已保存')
      setCfgModal(null)
      load()
    } catch (e) {
      message.error(e?.response?.data?.detail || '保存失败')
    }
  }

  const submitSilence = async () => {
    const values = await silenceForm.validateFields()
    try {
      await createSilence(values)
      message.success('静默窗口已创建')
      setSilenceModal(false)
      silenceForm.resetFields()
      load()
    } catch (e) {
      message.error(e?.response?.data?.detail || '创建失败')
    }
  }

  const doTest = async (cfg) => {
    try {
      const { data } = await testAlertConfig(cfg.id, cfg.min_severity || 'warning')
      if (data.ok) message.success('测试消息已送达')
      else if (!data.configured) message.warning('该渠道还没填 Webhook 地址')
      else message.error('发送失败，请检查 Webhook 地址与网络')
    } catch (e) {
      message.error(e?.response?.data?.detail || '测试失败')
    }
  }

  const eventColumns = [
    {
      title: '级别', dataIndex: 'severity', width: 90,
      render: (v) => <Tag color={SEVERITY[v]?.color}>{SEVERITY[v]?.label || v}</Tag>,
    },
    { title: '告警内容', dataIndex: 'title' },
    {
      title: '状态', dataIndex: 'status', width: 100,
      render: (v) => v === 'firing'
        ? <Badge status="processing" text="未恢复" />
        : <Badge status="success" text="已恢复" />,
    },
    { title: '次数', dataIndex: 'occurrences', width: 70 },
    { title: '首次发生', dataIndex: 'first_seen_at', width: 170, render: fmt },
    { title: '最近发生', dataIndex: 'last_seen_at', width: 170, render: fmt },
    {
      title: '最近通知', dataIndex: 'last_notified_at', width: 170,
      render: (v) => v ? fmt(v) : <span style={{ color: '#bbb' }}>未通知</span>,
    },
    {
      title: '操作', width: 120, render: (_, r) => r.status === 'firing' ? (
        <Popconfirm title="确认问题已解决？将标记为已恢复（不发恢复通知）"
          onConfirm={async () => { await resolveAlertEvent(r.id); load() }}>
          <Button type="link" size="small" icon={<CheckCircleOutlined />}>标记恢复</Button>
        </Popconfirm>
      ) : <span style={{ color: '#bbb' }}>-</span>,
    },
  ]

  const cfgColumns = [
    { title: '名称', dataIndex: 'name' },
    { title: '渠道', dataIndex: 'channel', render: (v) => <Tag color="geekblue">{v}</Tag> },
    {
      title: '最低级别', dataIndex: 'min_severity',
      render: (v) => <Tag color={SEVERITY[v]?.color}>{SEVERITY[v]?.label || v}</Tag>,
    },
    {
      title: '重复提醒', dataIndex: 'repeat_interval_minutes',
      render: (v) => (v ? `每 ${v} 分钟` : '仅状态变化时'),
    },
    {
      title: 'Webhook', dataIndex: 'webhook_url',
      render: (v) => v ? <Tooltip title={v}>{v.slice(0, 42)}…</Tooltip>
        : <span style={{ color: '#bbb' }}>未配置</span>,
    },
    { title: '启用', dataIndex: 'enabled', render: (v) => v ? <Tag color="green">是</Tag> : <Tag>否</Tag> },
    {
      title: '操作', width: 190, render: (_, r) => (
        <Space size={0}>
          <Button type="link" size="small" icon={<SendOutlined />} onClick={() => doTest(r)}>测试</Button>
          <Button type="link" size="small" onClick={() => openConfig(r)}>编辑</Button>
          <Popconfirm title="确定删除该渠道？" onConfirm={async () => { await deleteAlertConfig(r.id); load() }}>
            <Button type="link" danger size="small">删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const silenceColumns = [
    { title: '名称', dataIndex: 'name' },
    {
      title: '范围', dataIndex: 'scope',
      render: (v) => v
        ? <Tag color="orange">{plans.find((p) => p.id === v)?.name || v}</Tag>
        : <Tag color="purple">全局</Tag>,
    },
    { title: '开始', dataIndex: 'starts_at', width: 170, render: fmt },
    { title: '结束', dataIndex: 'ends_at', width: 170, render: fmt },
    {
      title: '状态', dataIndex: 'active',
      render: (v) => v ? <Tag color="green">生效中</Tag> : <Tag>已结束</Tag>,
    },
    { title: '原因', dataIndex: 'reason' },
    {
      title: '操作', width: 90, render: (_, r) => (
        <Popconfirm title="提前结束该静默？" onConfirm={async () => { await deleteSilence(r.id); load() }}>
          <Button type="link" danger size="small">解除</Button>
        </Popconfirm>
      ),
    },
  ]

  return (
    <div>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space size={40} wrap>
          <Statistic title="未恢复告警" value={summary?.active ?? 0}
            valueStyle={{ color: summary?.active ? '#cf1322' : '#3f8600' }} />
          <Statistic title="严重" value={summary?.by_severity?.critical ?? 0} valueStyle={{ color: '#cf1322' }} />
          <Statistic title="警告" value={summary?.by_severity?.warning ?? 0} valueStyle={{ color: '#d46b08' }} />
          <Statistic title="提示" value={summary?.by_severity?.info ?? 0} valueStyle={{ color: '#0958d9' }} />
          <Statistic title="生效中静默" value={summary?.silenced ?? 0} />
        </Space>
      </Card>

      <Card
        title={<span><BellOutlined /> 告警中心</span>}
        extra={<Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>}
      >
        <Tabs
          items={[
            {
              key: 'events', label: '告警事件',
              children: (
                <div>
                  <Space style={{ marginBottom: 12 }}>
                    <Select
                      value={statusFilter} onChange={setStatusFilter} style={{ width: 140 }}
                      options={[
                        { label: '未恢复', value: 'firing' },
                        { label: '已恢复', value: 'resolved' },
                        { label: '全部', value: 'all' },
                      ]}
                    />
                    <span style={{ color: '#8c8c8c' }}>
                      同一资源连续异常只提醒一次，恢复时自动补发恢复通知
                    </span>
                  </Space>
                  <Table rowKey="id" dataSource={events} columns={eventColumns}
                    loading={loading} size="middle"
                    expandable={{
                      expandedRowRender: (r) => (
                        <Descriptions size="small" column={2} bordered>
                          {Object.entries(r.detail || {}).map(([k, v]) => (
                            <Descriptions.Item key={k} label={k}>{String(v)}</Descriptions.Item>
                          ))}
                        </Descriptions>
                      ),
                    }} />
                </div>
              ),
            },
            {
              key: 'configs', label: '通知渠道',
              children: (
                <div>
                  <Space style={{ marginBottom: 12 }}>
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => openConfig(null)}>
                      添加渠道
                    </Button>
                    <span style={{ color: '#8c8c8c' }}>
                      按「最低级别」做分级路由：严重告警可只推给值班群，提示类进普通群
                    </span>
                  </Space>
                  <Table rowKey="id" dataSource={configs} columns={cfgColumns} loading={loading} />
                </div>
              ),
            },
            {
              key: 'silences', label: <span><MutedOutlined /> 静默窗口</span>,
              children: (
                <div>
                  <Space style={{ marginBottom: 12 }}>
                    <Button icon={<PlusOutlined />} onClick={() => setSilenceModal(true)}>新建静默</Button>
                    <span style={{ color: '#8c8c8c' }}>
                      维护窗口内的告警只记录不推送，避免变更期被误报刷屏
                    </span>
                  </Space>
                  <Table rowKey="id" dataSource={silences} columns={silenceColumns} loading={loading} />
                </div>
              ),
            },
          ]}
        />
      </Card>

      <Modal title={cfgModal?.id ? '编辑通知渠道' : '添加通知渠道'} open={!!cfgModal}
        onOk={submitConfig} onCancel={() => setCfgModal(null)} destroyOnClose>
        <Form form={cfgForm} layout="vertical"
          initialValues={{ channel: 'webhook', enabled: true, min_severity: 'info', repeat_interval_minutes: 0 }}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请填写名称' }]}>
            <Input placeholder="如：值班钉钉群" />
          </Form.Item>
          <Form.Item name="channel" label="渠道">
            <Select options={CHANNELS} />
          </Form.Item>
          <Form.Item name="webhook_url" label="Webhook 地址"
            extra="钉钉/企微机器人地址；留空则只记录日志不实际发送">
            <Input placeholder="https://oapi.dingtalk.com/robot/send?access_token=..." />
          </Form.Item>
          <Form.Item name="min_severity" label="最低推送级别"
            extra="只向该渠道推送不低于此级别的告警">
            <Select options={[
              { label: '提示及以上（全部）', value: 'info' },
              { label: '警告及以上', value: 'warning' },
              { label: '仅严重', value: 'critical' },
            ]} />
          </Form.Item>
          <Form.Item name="repeat_interval_minutes" label="重复提醒间隔（分钟）"
            extra="0 = 只在告警产生与恢复各提醒一次">
            <InputNumber min={0} max={1440} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="新建静默窗口" open={silenceModal} onOk={submitSilence}
        onCancel={() => setSilenceModal(false)} destroyOnClose>
        <Alert type="info" showIcon style={{ marginBottom: 16 }}
          message="静默期内产生的告警仍会记录在「告警事件」中，只是不推送消息。" />
        <Form form={silenceForm} layout="vertical" initialValues={{ scope: '', minutes: 60 }}>
          <Form.Item name="name" label="名称"><Input placeholder="如：数据库升级维护" /></Form.Item>
          <Form.Item name="scope" label="静默范围">
            <Select options={[
              { label: '全局（所有告警）', value: '' },
              ...plans.map((p) => ({ label: `仅计划：${p.name}`, value: p.id })),
            ]} />
          </Form.Item>
          <Form.Item name="minutes" label="持续时长（分钟）" rules={[{ required: true }]}>
            <InputNumber min={1} max={43200} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="reason" label="原因"><Input placeholder="变更单号 / 维护说明" /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
