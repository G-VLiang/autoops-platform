import { useEffect, useState } from 'react'
import { Card, Table, Button, Modal, Form, Input, Select, Tag, Space, Popconfirm, message, Tabs } from 'antd'
import { PlusOutlined, KeyOutlined, SafetyOutlined } from '@ant-design/icons'
import { listCredentials, createCredential, deleteCredential, listAudit } from '../api/modules'

const actionColor = { create: 'green', delete: 'red', execute: 'blue', login: 'default', update: 'orange' }
const actionLabel = { create: '创建', delete: '删除', execute: '执行', login: '登录', update: '更新' }

export default function Security() {
  const [credentials, setCredentials] = useState([])
  const [audit, setAudit] = useState([])
  const [modal, setModal] = useState(false)
  const [form] = Form.useForm()

  const load = () => {
    listCredentials().then((r) => setCredentials(r.data)).catch(() => {})
    listAudit().then((r) => setAudit(r.data)).catch(() => {})
  }

  useEffect(load, [])

  const submit = async () => {
    const values = await form.validateFields()
    await createCredential(values)
    message.success('凭据已创建（已加密存储）')
    setModal(false)
    form.resetFields()
    load()
  }

  const credColumns = [
    { title: '名称', dataIndex: 'name' },
    { title: '类型', dataIndex: 'type', render: (v) => <Tag color={v === 'key' ? 'purple' : 'blue'}>{v}</Tag> },
    { title: '用户名', dataIndex: 'username' },
    { title: '创建时间', dataIndex: 'created_at', render: (v) => new Date(v).toLocaleString() },
    {
      title: '操作', render: (_, r) => (
        <Popconfirm title="确定删除该凭据？" onConfirm={async () => { await deleteCredential(r.id); load() }}>
          <Button type="link" danger size="small">删除</Button>
        </Popconfirm>
      ),
    },
  ]

  const auditColumns = [
    { title: '用户', dataIndex: 'username' },
    { title: '操作', dataIndex: 'action', render: (v) => <Tag color={actionColor[v]}>{actionLabel[v] || v}</Tag> },
    { title: '资源', dataIndex: 'resource', render: (v, r) => `${v}${r.resource_id ? '#' + r.resource_id.slice(0, 8) : ''}` },
    { title: '详情', dataIndex: 'detail' },
    { title: '时间', dataIndex: 'created_at', render: (v) => new Date(v).toLocaleString() },
  ]

  return (
    <Card
      title="安全与审计"
    >
      <Tabs
        items={[
          {
            key: 'credentials', label: <span><KeyOutlined /> 凭据管理</span>,
            children: (
              <div>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setModal(true)} style={{ marginBottom: 12 }}>新建凭据</Button>
                <Table rowKey="id" dataSource={credentials} columns={credColumns} />
              </div>
            ),
          },
          {
            key: 'audit', label: <span><SafetyOutlined /> 审计日志</span>,
            children: <Table rowKey="id" dataSource={audit} columns={auditColumns} />,
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
          <Form.Item name="secret" label={form.getFieldValue('type') === 'key' ? '私钥内容' : '密码'} rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
