import { useEffect, useState } from 'react'
import {
  Button, Card, DatePicker, Descriptions, Form, Input, Modal, Popconfirm, Select, Space,
  Table, Tabs, Tag, message,
} from 'antd'
import {
  DownloadOutlined, KeyOutlined, ReloadOutlined, SafetyOutlined, SearchOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  auditExportPath, auditFacets, createCredential, deleteCredential, getSystemStatus,
  listAudit, listCredentials, reloadScheduler,
} from '../api/modules'
import { download } from '../api/index'

const actionColor = { create: 'green', delete: 'red', execute: 'blue', login: 'default', update: 'orange' }
const actionLabel = { create: '创建', delete: '删除', execute: '执行', login: '登录', update: '更新' }
const roleColor = { leader: 'green', standby: 'orange', disabled: 'default' }

export default function Security() {
  const [credentials, setCredentials] = useState([])
  const [audit, setAudit] = useState([])
  const [auditTotal, setAuditTotal] = useState(0)
  const [auditLoading, setAuditLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filters, setFilters] = useState({})
  const [facets, setFacets] = useState({ users: [], actions: [], resources: [] })
  const [status, setStatus] = useState(null)
  const [modal, setModal] = useState(false)
  const [form] = Form.useForm()

  const loadStatic = () => {
    listCredentials().then((r) => setCredentials(r.data)).catch(() => {})
    getSystemStatus().then((r) => setStatus(r.data)).catch(() => {})
    auditFacets().then((r) => setFacets(r.data)).catch(() => {})
  }

  const loadAudit = (p = page, size = pageSize, f = filters) => {
    setAuditLoading(true)
    const params = { page: p, size, ...f }
    // 时间范围转成后端可解析的起止时间
    if (f.range?.length === 2) {
      params.start = f.range[0].startOf('day').format('YYYY-MM-DD HH:mm:ss')
      params.end = f.range[1].endOf('day').format('YYYY-MM-DD HH:mm:ss')
    }
    delete params.range
    listAudit(params)
      .then((r) => {
        setAudit(r.data.items || [])
        setAuditTotal(r.data.total || 0)
      })
      .catch(() => {})
      .finally(() => setAuditLoading(false))
  }

  useEffect(() => {
    loadStatic()
    loadAudit(1, 20, {})
  }, [])

  const submit = async () => {
    const values = await form.validateFields()
    try {
      await createCredential(values)
      message.success('凭据已创建（已加密存储）')
      setModal(false)
      form.resetFields()
      loadStatic()
    } catch (e) {
      message.error(e?.response?.data?.detail || '创建失败')
    }
  }

  const reload = async () => {
    try {
      await reloadScheduler()
      message.success('调度作业已重建')
      loadStatic()
    } catch (e) {
      message.error(e?.response?.data?.detail || '重建失败')
    }
  }

  const doSearch = () => {
    setPage(1)
    loadAudit(1, pageSize, filters)
  }

  const doReset = () => {
    setFilters({})
    setPage(1)
    loadAudit(1, pageSize, {})
  }

  const doExport = async () => {
    setAuditLoading(true)
    try {
      const params = { ...filters }
      if (params.range?.length === 2) {
        params.start = params.range[0].startOf('day').format('YYYY-MM-DD HH:mm:ss')
        params.end = params.range[1].endOf('day').format('YYYY-MM-DD HH:mm:ss')
      }
      delete params.range
      await download(auditExportPath(params), `审计日志-${dayjs().format('YYYYMMDD')}.csv`)
      message.success('审计日志已导出')
    } catch (e) {
      message.error('导出失败')
    } finally {
      setAuditLoading(false)
    }
  }

  const credColumns = [
    { title: '名称', dataIndex: 'name' },
    { title: '类型', dataIndex: 'type', render: (v) => <Tag color={v === 'key' ? 'purple' : 'blue'}>{v}</Tag> },
    { title: '用户名', dataIndex: 'username' },
    { title: '创建时间', dataIndex: 'created_at', render: (v) => new Date(v).toLocaleString() },
    {
      title: '操作', render: (_, r) => (
        <Popconfirm title="确定删除该凭据？" onConfirm={async () => { await deleteCredential(r.id); loadStatic() }}>
          <Button type="link" danger size="small">删除</Button>
        </Popconfirm>
      ),
    },
  ]

  const auditColumns = [
    { title: '用户', dataIndex: 'username', width: 120 },
    {
      title: '操作', dataIndex: 'action', width: 90,
      render: (v) => <Tag color={actionColor[v]}>{actionLabel[v] || v}</Tag>,
    },
    {
      title: '资源', dataIndex: 'resource', width: 160,
      render: (v, r) => `${v}${r.resource_id ? '#' + r.resource_id.slice(0, 8) : ''}`,
    },
    { title: '详情', dataIndex: 'detail' },
    { title: '来源IP', dataIndex: 'ip', width: 130, render: (v) => v || '-' },
    {
      title: '时间', dataIndex: 'created_at', width: 175,
      render: (v) => new Date(v).toLocaleString(),
    },
  ]

  const sch = status?.scheduler || {}
  const art = status?.artifact || {}
  const prov = status?.auth_providers || {}

  return (
    <Card title="安全与审计">
      <Tabs
        items={[
          {
            key: 'credentials', label: <span><KeyOutlined /> 凭据管理</span>,
            children: (
              <div>
                <Button type="primary" icon={<KeyOutlined />} onClick={() => setModal(true)}
                  style={{ marginBottom: 12 }}>新建凭据</Button>
                <Table rowKey="id" dataSource={credentials} columns={credColumns} />
              </div>
            ),
          },
          {
            key: 'audit', label: <span><SafetyOutlined /> 审计日志</span>,
            children: (
              <div>
                <Space wrap style={{ marginBottom: 12 }}>
                  <Select
                    allowClear placeholder="用户" style={{ width: 130 }}
                    value={filters.username}
                    onChange={(v) => setFilters({ ...filters, username: v })}
                    options={facets.users.map((u) => ({ label: u, value: u }))}
                  />
                  <Select
                    allowClear placeholder="操作类型" style={{ width: 130 }}
                    value={filters.action}
                    onChange={(v) => setFilters({ ...filters, action: v })}
                    options={facets.actions.map((a) => ({
                      label: actionLabel[a] || a, value: a,
                    }))}
                  />
                  <Select
                    allowClear placeholder="资源类型" style={{ width: 140 }}
                    value={filters.resource}
                    onChange={(v) => setFilters({ ...filters, resource: v })}
                    options={facets.resources.map((r) => ({ label: r, value: r }))}
                  />
                  <Input
                    allowClear prefix={<SearchOutlined />} placeholder="关键词（详情/ID）"
                    style={{ width: 200 }}
                    value={filters.keyword}
                    onChange={(e) => setFilters({ ...filters, keyword: e.target.value })}
                    onPressEnter={doSearch}
                  />
                  <DatePicker.RangePicker
                    value={filters.range}
                    onChange={(v) => setFilters({ ...filters, range: v })}
                    placeholder={['开始日期', '结束日期']}
                  />
                  <Button type="primary" onClick={doSearch}>查询</Button>
                  <Button onClick={doReset}>重置</Button>
                  <Button icon={<DownloadOutlined />} onClick={doExport} loading={auditLoading}>
                    导出 CSV
                  </Button>
                </Space>
                <Table
                  rowKey="id" dataSource={audit} columns={auditColumns} loading={auditLoading}
                  size="middle"
                  pagination={{
                    current: page, pageSize, total: auditTotal, showSizeChanger: true,
                    showTotal: (t) => `共 ${t} 条`,
                    onChange: (p, s) => { setPage(p); setPageSize(s); loadAudit(p, s, filters) },
                  }}
                />
              </div>
            ),
          },
          {
            key: 'system', label: <span><SettingOutlined /> 系统状态</span>,
            children: (
              <div>
                <Space style={{ marginBottom: 12 }}>
                  <Button icon={<ReloadOutlined />} onClick={reload}>重建调度作业</Button>
                  <Button onClick={loadStatic}>刷新状态</Button>
                </Space>
                <Descriptions bordered size="small" column={2}>
                  <Descriptions.Item label="实例 ID">{status?.instance_id || '-'}</Descriptions.Item>
                  <Descriptions.Item label="调度角色">
                    <Tag color={roleColor[sch.role]}>{sch.role || '-'}</Tag>
                    {sch.role === 'standby' && <span style={{ color: '#8c8c8c' }}>
                      其他实例持有租约，本实例待命
                    </span>}
                  </Descriptions.Item>
                  <Descriptions.Item label="已注册作业">{sch.jobs ?? 0} 个</Descriptions.Item>
                  <Descriptions.Item label="租约到期">{sch.lease_until || '-'}</Descriptions.Item>
                  <Descriptions.Item label="租约 TTL / 心跳">
                    {sch.lease_ttl_seconds ?? '-'}s / {sch.heartbeat_seconds ?? '-'}s
                  </Descriptions.Item>
                  <Descriptions.Item label="数据库">{status?.database || '-'}</Descriptions.Item>
                  <Descriptions.Item label="执行器">{status?.executor || '-'}</Descriptions.Item>
                  <Descriptions.Item label="产物存储">
                    <Tag color="cyan">{art.backend || '-'}</Tag>
                    {art.backend === 'local' ? art.dir : art.bucket}
                    <span style={{ color: '#8c8c8c' }}> · 保留 {art.retention_days} 天</span>
                  </Descriptions.Item>
                  <Descriptions.Item label="登录方式">
                    <Space size={4}>
                      <Tag color="blue">本地</Tag>
                      {prov.ldap && <Tag color="green">LDAP</Tag>}
                      {prov.oidc && <Tag color="purple">OIDC</Tag>}
                    </Space>
                  </Descriptions.Item>
                </Descriptions>
              </div>
            ),
          },
        ]}
      />

      <Modal title="新建凭据" open={modal} onOk={submit} onCancel={() => setModal(false)}>
        <Form form={form} layout="vertical" initialValues={{ type: 'password', username: 'root' }}>
          <Form.Item name="name" label="凭据名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="type" label="类型">
            <Select options={[{ label: '密码', value: 'password' }, { label: '私钥', value: 'key' }]} />
          </Form.Item>
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="secret" label="密码 / 私钥内容" rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
