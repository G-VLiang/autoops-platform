import { useEffect, useState } from 'react'
import {
  App, Button, Card, Form, Input, Modal, Space, Switch, Table, Tag, Typography,
} from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { createTenant, listTenants, updateTenant } from '../api/modules'

const { Text } = Typography

export default function Tenants() {
  const { message } = App.useApp()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      setRows((await listTenants()).data || [])
    } catch (e) {
      message.error(e?.response?.data?.detail || '加载租户失败（需要平台超管权限）')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    setOpen(true)
  }

  const openEdit = (row) => {
    setEditing(row)
    form.setFieldsValue({ code: row.code, name: row.name, description: row.description, enabled: row.enabled })
    setOpen(true)
  }

  const submit = async () => {
    const values = await form.validateFields()
    try {
      if (editing) {
        await updateTenant(editing.id, values)
        message.success('租户已更新')
      } else {
        await createTenant(values)
        message.success('租户已创建')
      }
      setOpen(false)
      load()
    } catch (e) {
      message.error(e?.response?.data?.detail || '保存失败')
    }
  }

  const toggle = async (row, enabled) => {
    try {
      await updateTenant(row.id, {
        code: row.code, name: row.name, description: row.description, enabled,
      })
      message.success(enabled ? '租户已启用' : '租户已停用（该租户用户将无法登录）')
      load()
    } catch (e) {
      message.error(e?.response?.data?.detail || '操作失败')
    }
  }

  return (
    <Card
      title="租户管理"
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建租户</Button>
        </Space>
      }
    >
      <Text type="secondary">
        每个租户拥有独立的资产、任务、巡检与审计数据；停用后该租户用户无法登录，平台超管不受影响。
      </Text>
      <Table
        style={{ marginTop: 12 }}
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={false}
        columns={[
          { title: '租户编码', dataIndex: 'code', width: 160,
            render: (v) => <Tag color={v === 'default' ? 'gold' : 'blue'}>{v}</Tag> },
          { title: '名称', dataIndex: 'name' },
          { title: '描述', dataIndex: 'description', ellipsis: true },
          { title: '用户', dataIndex: 'user_count', width: 90, align: 'right' },
          { title: '主机', dataIndex: 'host_count', width: 90, align: 'right' },
          { title: '状态', dataIndex: 'enabled', width: 110,
            render: (v, r) => (
              <Switch size="small" checked={v} disabled={r.code === 'default'}
                onChange={(checked) => toggle(r, checked)} />
            ) },
          { title: '创建时间', dataIndex: 'created_at', width: 170,
            render: (v) => (v ? new Date(v).toLocaleString() : '-') },
          { title: '操作', width: 90,
            render: (_, r) => <a onClick={() => openEdit(r)}>编辑</a> },
        ]}
      />

      <Modal title={editing ? '编辑租户' : '新建租户'} open={open} onCancel={() => setOpen(false)}
        onOk={submit} okText="保存" destroyOnClose>
        <Form form={form} layout="vertical" initialValues={{ enabled: true }}>
          <Form.Item name="code" label="租户编码" rules={[
            { required: true, message: '请输入租户编码' },
            { pattern: /^[a-zA-Z0-9_-]{2,32}$/, message: '2-32 位字母、数字、下划线或短横线' },
          ]}>
            <Input placeholder="如 acme" disabled={Boolean(editing)} />
          </Form.Item>
          <Form.Item name="name" label="租户名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如 ACME 科技有限公司" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="可选" />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
