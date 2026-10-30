import { useEffect, useState } from 'react'
import {
  Card, Table, Button, Modal, Form, Input, Select, Tag, Space, Popconfirm, message, Tabs,
  Tooltip, Statistic, Alert,
} from 'antd'
import { PlusOutlined, RadarChartOutlined, SyncOutlined } from '@ant-design/icons'
import {
  listHosts, listGroups, createHost, createGroup, deleteHost, probeHosts, probeHost,
} from '../api/modules'

const STATUS = {
  online: { color: 'success', text: '在线' },
  offline: { color: 'error', text: '离线' },
  unknown: { color: 'default', text: '未知' },
}

export default function Hosts() {
  const [hosts, setHosts] = useState([])
  const [groups, setGroups] = useState([])
  const [hostModal, setHostModal] = useState(false)
  const [groupModal, setGroupModal] = useState(false)
  const [probing, setProbing] = useState(false)
  const [probingId, setProbingId] = useState('')
  const [lastProbe, setLastProbe] = useState(null)
  const [form] = Form.useForm()
  const [groupForm] = Form.useForm()

  const load = () => {
    listHosts().then((r) => setHosts(r.data)).catch(() => {})
    listGroups().then((r) => setGroups(r.data)).catch(() => {})
  }

  useEffect(load, [])

  const submitHost = async () => {
    const values = await form.validateFields()
    // 标签在表单里用逗号分隔输入，提交前转成数组
    const tags = typeof values.tags === 'string'
      ? values.tags.split(',').map((t) => t.trim()).filter(Boolean)
      : (values.tags || [])
    await createHost({ ...values, tags, port: Number(values.port) || 22 })
    message.success('主机已添加')
    setHostModal(false)
    form.resetFields()
    load()
  }

  const submitGroup = async () => {
    const values = await groupForm.validateFields()
    await createGroup(values)
    message.success('主机组已创建')
    setGroupModal(false)
    groupForm.resetFields()
    load()
  }

  const probeAll = async () => {
    setProbing(true)
    try {
      const { data } = await probeHosts({})
      setLastProbe(data)
      if (data.total === 0) {
        message.info('还没有主机可探测')
      } else {
        message.success(
          `探测完成：${data.online}/${data.total} 台在线，耗时 ${(data.elapsed_ms / 1000).toFixed(1)}s`,
        )
      }
      load()
    } catch (e) {
      message.error(e?.response?.data?.detail || '探测失败')
    } finally {
      setProbing(false)
    }
  }

  const probeOne = async (row) => {
    setProbingId(row.id)
    try {
      const { data } = await probeHost(row.id)
      message[data.online ? 'success' : 'warning'](
        `${row.hostname}: ${data.online ? '在线' : '离线'}（${data.message}）`,
      )
      load()
    } catch (e) {
      message.error(e?.response?.data?.detail || '探测失败')
    } finally {
      setProbingId('')
    }
  }

  const groupOptions = groups.map((g) => ({ label: g.name, value: g.id }))

  const hostColumns = [
    { title: '主机名', dataIndex: 'hostname' },
    { title: 'IP', dataIndex: 'ip' },
    { title: '端口', dataIndex: 'port', width: 70 },
    { title: '系统', dataIndex: 'os_type', width: 90 },
    {
      title: '状态', dataIndex: 'status', width: 110,
      render: (v, r) => {
        const s = STATUS[v] || STATUS.unknown
        if (!r.probe_at) return <Tag color={s.color}>{s.text}</Tag>
        return (
          <Tooltip title={
            `${r.probe_message || '-'}｜探测于 ${new Date(r.probe_at).toLocaleString()}${r.probe_latency_ms != null ? `｜延迟 ${r.probe_latency_ms}ms` : ''
            }`
          }>
            <Tag color={s.color}>
              {s.text}{r.probe_latency_ms != null ? ` ${r.probe_latency_ms}ms` : ''}
            </Tag>
          </Tooltip>
        )
      },
    },
    {
      title: '最后在线', dataIndex: 'last_seen', width: 170,
      render: (v) => v ? new Date(v).toLocaleString() : <span style={{ color: '#bbb' }}>从未</span>,
    },
    {
      title: '标签', dataIndex: 'tags',
      render: (t) => (t || []).map((x) => <Tag key={x} color="blue">{x}</Tag>),
    },
    { title: '主机组', dataIndex: 'group_name', render: (v) => v || '-' },
    {
      title: '操作', width: 150, render: (_, r) => (
        <Space size={0}>
          <Button type="link" size="small" icon={<RadarChartOutlined />}
            loading={probingId === r.id} onClick={() => probeOne(r)}>探测</Button>
          <Popconfirm title="确定删除该主机？" onConfirm={async () => { await deleteHost(r.id); load() }}>
            <Button type="link" danger size="small">删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const groupColumns = [
    { title: '组名', dataIndex: 'name' },
    { title: '描述', dataIndex: 'description' },
    { title: '主机数', dataIndex: 'host_count' },
  ]

  const onlineCount = hosts.filter((h) => h.status === 'online').length
  const offlineCount = hosts.filter((h) => h.status === 'offline').length

  return (
    <div>
      <Card
        title="资产管理 (CMDB)"
        extra={
          <Space>
            <Button icon={<SyncOutlined />} onClick={probeAll} loading={probing}>立即探测</Button>
            <Button icon={<PlusOutlined />} onClick={() => setGroupModal(true)}>新建主机组</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setHostModal(true)}>添加主机</Button>
          </Space>
        }
      >
        <Space size={40} style={{ marginBottom: 16 }} wrap>
          <Statistic title="主机总数" value={hosts.length} />
          <Statistic title="在线" value={onlineCount} valueStyle={{ color: '#3f8600' }} />
          <Statistic title="离线" value={offlineCount} valueStyle={{ color: '#cf1322' }} />
          <Statistic title="未探测" value={hosts.length - onlineCount - offlineCount}
            valueStyle={{ color: '#8c8c8c' }} />
        </Space>
        {lastProbe && (
          <Alert
            type={lastProbe.offline > 0 ? 'warning' : 'success'} showIcon
            style={{ marginBottom: 12 }}
            message={`本次探测 ${lastProbe.total} 台：在线 ${lastProbe.online}，离线 ${lastProbe.offline}，耗时 ${(lastProbe.elapsed_ms / 1000).toFixed(1)}s`}
            closable onClose={() => setLastProbe(null)}
          />
        )}
        <Tabs
          items={[
            { key: 'hosts', label: '主机列表', children: <Table rowKey="id" dataSource={hosts} columns={hostColumns} /> },
            { key: 'groups', label: '主机组', children: <Table rowKey="id" dataSource={groups} columns={groupColumns} /> },
          ]}
        />
      </Card>

      <Modal title="添加主机" open={hostModal} onOk={submitHost} onCancel={() => setHostModal(false)}>
        <Form form={form} layout="vertical" initialValues={{ port: 22, os_type: 'linux' }}>
          <Form.Item name="hostname" label="主机名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="ip" label="IP 地址" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="port" label="端口"><Input type="number" /></Form.Item>
          <Form.Item name="os_type" label="系统类型">
            <Select options={[{ label: 'Linux', value: 'linux' }, { label: 'Windows', value: 'windows' }]} />
          </Form.Item>
          <Form.Item name="os_version" label="系统版本"><Input /></Form.Item>
          <Form.Item name="group_id" label="所属主机组"><Select options={groupOptions} allowClear /></Form.Item>
          <Form.Item name="tags" label="标签（逗号分隔）"><Input placeholder="web,db,redis" /></Form.Item>
        </Form>
      </Modal>

      <Modal title="新建主机组" open={groupModal} onOk={submitGroup} onCancel={() => setGroupModal(false)}>
        <Form form={groupForm} layout="vertical">
          <Form.Item name="name" label="组名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="描述"><Input /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
