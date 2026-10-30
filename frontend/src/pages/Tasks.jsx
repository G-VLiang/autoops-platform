import { useEffect, useMemo, useState } from 'react'
import {
  Card, Table, Button, Modal, Form, Input, InputNumber, Select, Tag, Space, Drawer, message,
  Descriptions, Tabs, Empty, List, Typography, Tooltip, Divider,
} from 'antd'
import { AppstoreOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import {
  listTasks, createTask, listGroups, listHosts, listTemplates, getTaskLogs,
  listLibrary, listLibraryCategories, createTaskFromLibrary,
} from '../api/modules'

const { Text, Paragraph } = Typography

const statusColor = {
  success: 'green', failed: 'red', partial: 'orange', running: 'blue', pending: 'default',
}

export default function Tasks() {
  const [tasks, setTasks] = useState([])
  const [groups, setGroups] = useState([])
  const [hosts, setHosts] = useState([])
  const [templates, setTemplates] = useState([])
  const [modal, setModal] = useState(false)
  const [libModal, setLibModal] = useState(false)
  const [libItems, setLibItems] = useState([])
  const [libCats, setLibCats] = useState([])
  const [libCat, setLibCat] = useState('')
  const [libKeyword, setLibKeyword] = useState('')
  const [libSelected, setLibSelected] = useState(null)
  const [libSubmitting, setLibSubmitting] = useState(false)
  const [drawer, setDrawer] = useState(null)
  const [logs, setLogs] = useState([])
  const [form] = Form.useForm()
  const [libForm] = Form.useForm()
  const [taskType, setTaskType] = useState('adhoc')

  const load = () => {
    listTasks().then((r) => setTasks(r.data)).catch(() => {})
    listGroups().then((r) => setGroups(r.data)).catch(() => {})
    listHosts().then((r) => setHosts(r.data)).catch(() => {})
    listTemplates().then((r) => setTemplates(r.data)).catch(() => {})
  }

  useEffect(load, [])

  const openLibrary = () => {
    setLibModal(true)
    setLibSelected(null)
    listLibraryCategories().then((r) => setLibCats(r.data)).catch(() => {})
    listLibrary({}).then((r) => setLibItems(r.data)).catch(() => {})
  }

  const filterLibrary = (cat, kw) => {
    setLibCat(cat)
    setLibKeyword(kw)
    listLibrary({ category: cat || undefined, keyword: kw || undefined })
      .then((r) => setLibItems(r.data)).catch(() => {})
  }

  const submit = async () => {
    const values = await form.validateFields()
    try {
      await createTask(values)
      message.success('任务已提交执行')
      setModal(false)
      form.resetFields()
      load()
    } catch (e) {
      message.error(e?.response?.data?.detail || '提交失败')
    }
  }

  const submitLibrary = async () => {
    if (!libSelected) return
    const values = await libForm.validateFields()
    setLibSubmitting(true)
    try {
      await createTaskFromLibrary({ library_key: libSelected.key, ...values })
      message.success(`「${libSelected.name}」已执行`)
      setLibModal(false)
      libForm.resetFields()
      load()
    } catch (e) {
      message.error(e?.response?.data?.detail || '执行失败')
    } finally {
      setLibSubmitting(false)
    }
  }

  const viewLogs = async (task) => {
    const { data } = await getTaskLogs(task.id)
    setLogs(data)
    setDrawer(task)
  }

  const targetOptions = useMemo(() => [
    ...groups.map((g) => ({ label: `[组] ${g.name}`, value: g.id })),
    ...hosts.map((h) => ({ label: `[主机] ${h.hostname}`, value: h.id })),
  ], [groups, hosts])

  const columns = [
    { title: '名称', dataIndex: 'name' },
    { title: '类型', dataIndex: 'task_type', width: 110, render: (v) => <Tag color="geekblue">{v}</Tag> },
    {
      title: '状态', dataIndex: 'status', width: 110,
      render: (v, r) => (
        <Space size={4}>
          <Tag color={statusColor[v]}>{v}</Tag>
          {r.attempts > 1 && (
            <Tooltip title={`共执行 ${r.attempts} 次（最多重试 ${r.max_retries} 次）`}>
              <Tag color="purple">×{r.attempts}</Tag>
            </Tooltip>
          )}
        </Space>
      ),
    },
    {
      title: '结果', dataIndex: 'summary',
      render: (s) => s ? <Space size={4}>{Object.entries(s).map(([k, val]) => <Tag key={k}>{k}:{val}</Tag>)}</Space> : '-',
    },
    { title: '创建人', dataIndex: 'created_by', width: 130 },
    { title: '创建时间', dataIndex: 'created_at', width: 175, render: (v) => new Date(v).toLocaleString() },
    { title: '操作', width: 100, render: (_, r) => <Button type="link" size="small" onClick={() => viewLogs(r)}>查看日志</Button> },
  ]

  const renderContent = () => {
    if (taskType === 'inspection') {
      return (
        <Form.Item name="content" label="巡检模板" rules={[{ required: true }]}>
          <Select options={templates.map((t) => ({ label: t.name, value: t.id }))} />
        </Form.Item>
      )
    }
    if (taskType === 'playbook') {
      return (
        <Form.Item name="content" label="Playbook YAML" rules={[{ required: true }]}>
          <Input.TextArea rows={6} placeholder="- hosts: all&#10;  tasks: ..." />
        </Form.Item>
      )
    }
    return (
      <Form.Item name="content" label="命令" rules={[{ required: true }]}>
        <Input placeholder="例如：df -h" />
      </Form.Item>
    )
  }

  return (
    <div>
      <Card
        title="作业中心"
        extra={
          <Space>
            <Button icon={<AppstoreOutlined />} onClick={openLibrary}>从模板库创建</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setModal(true)}>新建任务</Button>
          </Space>
        }
      >
        <Table rowKey="id" dataSource={tasks} columns={columns} />
      </Card>

      {/* 新建任务 */}
      <Modal title="新建任务" open={modal} onOk={submit} onCancel={() => setModal(false)} width={620}>
        <Form form={form} layout="vertical"
          initialValues={{ task_type: 'adhoc', target_type: 'group', max_retries: 0, timeout_seconds: 0 }}>
          <Form.Item name="name" label="任务名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="task_type" label="任务类型" rules={[{ required: true }]}>
            <Select
              onChange={setTaskType}
              options={[
                { label: '批量命令 (adhoc)', value: 'adhoc' },
                { label: 'Playbook', value: 'playbook' },
                { label: '巡检执行', value: 'inspection' },
              ]}
            />
          </Form.Item>
          {renderContent()}
          <Form.Item name="target_type" label="目标类型">
            <Select options={[{ label: '主机组', value: 'group' }, { label: '单台主机', value: 'host' }]} />
          </Form.Item>
          <Form.Item name="target_id" label="目标" rules={[{ required: true }]}>
            <Select options={targetOptions} showSearch optionFilterProp="label" />
          </Form.Item>
          <Space size={16} style={{ display: 'flex' }}>
            <Form.Item name="max_retries" label="失败重试次数"
              tooltip="网络抖动导致的失败会在这里配置的次数内自动重试" style={{ flex: 1 }}>
              <InputNumber min={0} max={5} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="timeout_seconds" label="执行超时（秒）"
              tooltip="0 表示不限制；超时后中止后续主机执行" style={{ flex: 1 }}>
              <InputNumber min={0} max={7200} step={30} style={{ width: '100%' }} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>

      {/* 模板库 */}
      <Modal title="作业模板库" open={libModal} onCancel={() => setLibModal(false)}
        width={860} footer={null} destroyOnClose>
        <Space style={{ marginBottom: 12 }} wrap>
          <Select
            value={libCat} style={{ width: 150 }} placeholder="全部分类"
            onChange={(v) => filterLibrary(v, libKeyword)}
            options={[{ label: '全部分类', value: '' },
              ...libCats.map((c) => ({ label: `${c.category} (${c.count})`, value: c.category }))]}
          />
          <Input
            prefix={<SearchOutlined />} placeholder="搜索模板名称/标签" allowClear
            style={{ width: 260 }}
            onChange={(e) => filterLibrary(libCat, e.target.value)}
          />
          <Text type="secondary">共 {libItems.length} 个模板</Text>
        </Space>
        <div style={{ display: 'flex', gap: 16 }}>
          <div style={{ flex: 1, maxHeight: 420, overflow: 'auto', borderRight: '1px solid #f0f0f0', paddingRight: 12 }}>
            {libItems.length === 0 ? <Empty description="没有匹配的模板" /> : (
              <List
                size="small"
                dataSource={libItems}
                renderItem={(item) => (
                  <List.Item
                    onClick={() => setLibSelected(item)}
                    style={{
                      cursor: 'pointer', padding: '8px 10px', borderRadius: 6,
                      background: libSelected?.key === item.key ? '#e6f4ff' : 'transparent',
                    }}
                  >
                    <List.Item.Meta
                      title={<Space size={6}>{item.name}<Tag color="cyan">{item.category}</Tag></Space>}
                      description={<Text type="secondary" style={{ fontSize: 12 }}>{item.description}</Text>}
                    />
                  </List.Item>
                )}
              />
            )}
          </div>
          <div style={{ flex: 1 }}>
            {libSelected ? (
              <>
                <Paragraph strong>{libSelected.name}</Paragraph>
                <Paragraph type="secondary" style={{ fontSize: 12 }}>{libSelected.description}</Paragraph>
                <Form form={libForm} layout="vertical"
                  initialValues={{ target_type: 'group', max_retries: 0, timeout_seconds: 0 }}>
                  <Form.Item name="name" label="任务名称">
                    <Input placeholder={libSelected.name} />
                  </Form.Item>
                  <Form.Item name="target_type" label="目标类型">
                    <Select options={[{ label: '主机组', value: 'group' }, { label: '单台主机', value: 'host' }]} />
                  </Form.Item>
                  <Form.Item name="target_id" label="执行目标" rules={[{ required: true }]}>
                    <Select options={targetOptions} showSearch optionFilterProp="label" placeholder="选择主机组或主机" />
                  </Form.Item>
                  <Space size={16} style={{ display: 'flex' }}>
                    <Form.Item name="max_retries" label="失败重试" style={{ flex: 1 }}>
                      <InputNumber min={0} max={5} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="timeout_seconds" label="超时（秒）" style={{ flex: 1 }}>
                      <InputNumber min={0} max={7200} step={30} style={{ width: '100%' }} />
                    </Form.Item>
                  </Space>
                  <Button type="primary" block loading={libSubmitting} onClick={submitLibrary}>
                    立即执行
                  </Button>
                </Form>
                <Divider style={{ margin: '12px 0' }} />
                <Text type="secondary" style={{ fontSize: 12 }}>剧本预览</Text>
                <pre style={{
                  background: '#f6f8fa', padding: 8, fontSize: 11, maxHeight: 140,
                  overflow: 'auto', borderRadius: 6,
                }}>{libSelected.content}</pre>
              </>
            ) : (
              <Empty description="从左侧选择一个模板" style={{ marginTop: 60 }} />
            )}
          </div>
        </div>
      </Modal>

      <Drawer
        title={drawer ? `任务日志 - ${drawer.name}` : '任务日志'}
        open={!!drawer}
        onClose={() => setDrawer(null)}
        width={680}
      >
        {drawer && (
          <>
            <Descriptions column={2} size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="状态">
                <Tag color={statusColor[drawer.status]}>{drawer.status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="执行次数">
                {drawer.attempts || 1} 次（最多重试 {drawer.max_retries || 0} 次）
              </Descriptions.Item>
              <Descriptions.Item label="结果" span={2}>
                {Object.entries(drawer.summary || {}).map(([k, v]) => `${k}: ${v} `)}
              </Descriptions.Item>
              <Descriptions.Item label="超时设置" span={2}>
                {drawer.timeout_seconds ? `${drawer.timeout_seconds} 秒` : '不限制'}
              </Descriptions.Item>
            </Descriptions>
            {logs.map((l) => (
              <div key={l.id} style={{ border: '1px solid #f0f0f0', borderRadius: 6, padding: 8, marginBottom: 8 }}>
                <Space>
                  <Tag color={l.event === 'failed' ? 'red' : l.event === 'unreachable' ? 'volcano' : l.event === 'info' ? 'default' : 'green'}>
                    {l.event}
                  </Tag>
                  <b>{l.host}</b>
                </Space>
                <div style={{ color: '#888', fontSize: 12 }}>{l.message}</div>
                {l.stdout && <pre style={{ background: '#f6f8fa', padding: 8, fontSize: 12, overflow: 'auto' }}>{l.stdout}</pre>}
              </div>
            ))}
          </>
        )}
      </Drawer>
    </div>
  )
}
