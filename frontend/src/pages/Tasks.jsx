import { useEffect, useState } from 'react'
import { Card, Table, Button, Modal, Form, Input, Select, Tag, Space, Drawer, message, Descriptions } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { listTasks, createTask, listGroups, listHosts, listTemplates, getTaskLogs } from '../api/modules'

const statusColor = {
  success: 'green', failed: 'red', partial: 'orange', running: 'blue', pending: 'default',
}

export default function Tasks() {
  const [tasks, setTasks] = useState([])
  const [groups, setGroups] = useState([])
  const [hosts, setHosts] = useState([])
  const [templates, setTemplates] = useState([])
  const [modal, setModal] = useState(false)
  const [drawer, setDrawer] = useState(null)
  const [logs, setLogs] = useState([])
  const [form] = Form.useForm()
  const [taskType, setTaskType] = useState('adhoc')

  const load = () => {
    listTasks().then((r) => setTasks(r.data)).catch(() => {})
    listGroups().then((r) => setGroups(r.data)).catch(() => {})
    listHosts().then((r) => setHosts(r.data)).catch(() => {})
    listTemplates().then((r) => setTemplates(r.data)).catch(() => {})
  }

  useEffect(load, [])

  const submit = async () => {
    const values = await form.validateFields()
    await createTask(values)
    message.success('任务已提交执行')
    setModal(false)
    form.resetFields()
    load()
  }

  const viewLogs = async (task) => {
    const { data } = await getTaskLogs(task.id)
    setLogs(data)
    setDrawer(task)
  }

  const targetOptions = taskType === 'inspection'
    ? [] // 巡检按主机组/主机
    : []

  const columns = [
    { title: '名称', dataIndex: 'name' },
    { title: '类型', dataIndex: 'task_type', render: (v) => <Tag color="geekblue">{v}</Tag> },
    { title: '状态', dataIndex: 'status', render: (v) => <Tag color={statusColor[v]}>{v}</Tag> },
    { title: '结果', dataIndex: 'summary', render: (s) => s ? <Space size={4}>{Object.entries(s).map(([k, val]) => <Tag key={k}>{k}:{val}</Tag>)}</Space> : '-' },
    { title: '创建人', dataIndex: 'created_by' },
    { title: '创建时间', dataIndex: 'created_at', render: (v) => new Date(v).toLocaleString() },
    { title: '操作', render: (_, r) => <Button type="link" size="small" onClick={() => viewLogs(r)}>查看日志</Button> },
  ]

  return (
    <div>
      <Card
        title="作业中心"
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setModal(true)}>新建任务</Button>}
      >
        <Table rowKey="id" dataSource={tasks} columns={columns} />
      </Card>

      <Modal title="新建任务" open={modal} onOk={submit} onCancel={() => setModal(false)}>
        <Form form={form} layout="vertical" initialValues={{ task_type: 'adhoc', target_type: 'group' }}>
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
          {taskType === 'inspection' ? (
            <Form.Item name="content" label="巡检模板" rules={[{ required: true }]}>
              <Select options={templates.map((t) => ({ label: t.name, value: t.id }))} />
            </Form.Item>
          ) : taskType === 'playbook' ? (
            <Form.Item name="content" label="Playbook YAML" rules={[{ required: true }]}>
              <Input.TextArea rows={6} placeholder="- hosts: all&#10;  tasks: ..." />
            </Form.Item>
          ) : (
            <Form.Item name="content" label="命令" rules={[{ required: true }]}>
              <Input placeholder="例如：df -h" />
            </Form.Item>
          )}
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
        </Form>
      </Modal>

      <Drawer
        title={drawer ? `任务日志 - ${drawer.name}` : '任务日志'}
        open={!!drawer}
        onClose={() => setDrawer(null)}
        width={640}
      >
        {drawer && (
          <>
            <Descriptions column={1} size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="状态">
                <Tag color={statusColor[drawer.status]}>{drawer.status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="结果">
                {Object.entries(drawer.summary || {}).map(([k, v]) => `${k}: ${v} `)}
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
