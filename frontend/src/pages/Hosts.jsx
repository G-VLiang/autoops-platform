import { useEffect, useState } from 'react'
import { Card, Table, Button, Modal, Form, Input, Select, Tag, Space, Popconfirm, message, Tabs } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { listHosts, listGroups, createHost, createGroup, deleteHost } from '../api/modules'

export default function Hosts() {
  const [hosts, setHosts] = useState([])
  const [groups, setGroups] = useState([])
  const [hostModal, setHostModal] = useState(false)
  const [groupModal, setGroupModal] = useState(false)
  const [form] = Form.useForm()
  const [groupForm] = Form.useForm()

  const load = () => {
    listHosts().then((r) => setHosts(r.data)).catch(() => {})
    listGroups().then((r) => setGroups(r.data)).catch(() => {})
  }

  useEffect(load, [])

  const submitHost = async () => {
    const values = await form.validateFields()
    await createHost(values)
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

  const groupOptions = groups.map((g) => ({ label: g.name, value: g.id }))

  const hostColumns = [
    { title: '主机名', dataIndex: 'hostname' },
    { title: 'IP', dataIndex: 'ip' },
    { title: '端口', dataIndex: 'port' },
    { title: '系统', dataIndex: 'os_type' },
    { title: '版本', dataIndex: 'os_version' },
    { title: '状态', dataIndex: 'status', render: (v) => <Tag color={v === 'online' ? 'green' : 'default'}>{v}</Tag> },
    { title: '标签', dataIndex: 'tags', render: (t) => (t || []).map((x) => <Tag key={x} color="blue">{x}</Tag>) },
    { title: '主机组', dataIndex: 'group_name', render: (v) => v || '-' },
    {
      title: '操作', render: (_, r) => (
        <Popconfirm title="确定删除该主机？" onConfirm={async () => { await deleteHost(r.id); load() }}>
          <Button type="link" danger size="small">删除</Button>
        </Popconfirm>
      ),
    },
  ]

  const groupColumns = [
    { title: '组名', dataIndex: 'name' },
    { title: '描述', dataIndex: 'description' },
    { title: '主机数', dataIndex: 'host_count' },
  ]

  return (
    <div>
      <Card
        title="资产管理 (CMDB)"
        extra={
          <Space>
            <Button icon={<PlusOutlined />} onClick={() => setGroupModal(true)}>新建主机组</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setHostModal(true)}>添加主机</Button>
          </Space>
        }
      >
        <Tabs
          items={[
            { key: 'hosts', label: '主机列表', children: <Table rowKey="id" dataSource={hosts} columns={hostColumns} /> },
            { key: 'groups', label: '主机组', children: <Table rowKey="id" dataSource={groups} columns={groupColumns} /> },
          ]}
        />
      </Card>

      <Modal title="添加主机" open={hostModal} onOk={submitHost} onCancel={() => setHostModal(false)}>
        <Form form={form} layout="vertical">
          <Form.Item name="hostname" label="主机名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="ip" label="IP 地址" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="port" label="端口" initialValue={22}><Input type="number" /></Form.Item>
          <Form.Item name="os_type" label="系统类型" initialValue="linux">
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
