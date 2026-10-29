import { useEffect, useState } from 'react'
import { Card, Table, Button, Modal, Form, Input, Select, Tag, Space, Popconfirm, message, Tabs, Alert, Spin } from 'antd'
import { RobotOutlined, PlusOutlined, CheckOutlined } from '@ant-design/icons'
import { listTemplates, createTemplate, updateTemplate, deleteTemplate, generatePlaybook } from '../api/modules'

const catColor = { mysql: 'blue', redis: 'red', disk: 'purple', cpu: 'cyan', memory: 'gold', network: 'green', custom: 'default' }

export default function Inspections() {
  const [templates, setTemplates] = useState([])
  const [modal, setModal] = useState(false)
  const [genModal, setGenModal] = useState(false)
  const [genResult, setGenResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()
  const [genForm] = Form.useForm()

  const load = () => listTemplates().then((r) => setTemplates(r.data)).catch(() => {})

  useEffect(() => { load() }, [])

  const submit = async () => {
    const values = await form.validateFields()
    await createTemplate({ ...values, generated_by_llm: false, status: values.status || 'draft' })
    message.success('模板已创建')
    setModal(false)
    form.resetFields()
    load()
  }

  const doGenerate = async () => {
    const values = await genForm.validateFields()
    setLoading(true)
    try {
      const { data } = await generatePlaybook(values)
      setGenResult(data)
    } catch (e) {
      message.error(e.response?.data?.detail || '生成失败')
    } finally {
      setLoading(false)
    }
  }

  const saveGenerated = async () => {
    await createTemplate({
      name: genResult.name, description: genResult.description,
      category: genResult.category, playbook: genResult.playbook,
      generated_by_llm: true, status: 'draft',
    })
    message.success('已保存为巡检模板（草稿）')
    setGenModal(false)
    setGenResult(null)
    genForm.resetFields()
    load()
  }

  const approve = async (tpl) => {
    await updateTemplate(tpl.id, { name: tpl.name, description: tpl.description, category: tpl.category, playbook: tpl.playbook, generated_by_llm: tpl.generated_by_llm, status: 'approved' })
    message.success('已批准')
    load()
  }

  const columns = [
    { title: '名称', dataIndex: 'name' },
    { title: '分类', dataIndex: 'category', render: (v) => <Tag color={catColor[v]}>{v}</Tag> },
    { title: '描述', dataIndex: 'description' },
    { title: '来源', dataIndex: 'generated_by_llm', render: (v) => v ? <Tag icon={<RobotOutlined />} color="purple">AI 生成</Tag> : <Tag>手工</Tag> },
    { title: '状态', dataIndex: 'status', render: (v) => v === 'approved' ? <Tag color="green">已批准</Tag> : <Tag color="orange">草稿</Tag> },
    {
      title: '操作', render: (_, r) => (
        <Space>
          {r.status !== 'approved' && <Button type="link" size="small" icon={<CheckOutlined />} onClick={() => approve(r)}>批准</Button>}
          <Popconfirm title="确定删除？" onConfirm={async () => { await deleteTemplate(r.id); load() }}>
            <Button type="link" danger size="small">删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Card
        title="巡检中心"
        extra={
          <Space>
            <Button icon={<RobotOutlined />} onClick={() => setGenModal(true)}>AI 生成巡检脚本</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setModal(true)}>新建模板</Button>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="AI 生成的巡检脚本默认为「草稿」，需人工审查批准后方可在作业中心执行，保障生产安全。"
        />
        <Table rowKey="id" dataSource={templates} columns={columns} />
      </Card>

      {/* 手工新建模板 */}
      <Modal title="新建巡检模板" open={modal} onOk={submit} onCancel={() => setModal(false)} width={720}>
        <Form form={form} layout="vertical" initialValues={{ category: 'custom', status: 'draft' }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="描述"><Input /></Form.Item>
          <Form.Item name="category" label="分类">
            <Select options={['mysql', 'redis', 'disk', 'cpu', 'memory', 'network', 'custom'].map((c) => ({ label: c, value: c }))} />
          </Form.Item>
          <Form.Item name="playbook" label="Playbook YAML" rules={[{ required: true }]}>
            <Input.TextArea rows={10} placeholder="- hosts: all&#10;  tasks: ..." />
          </Form.Item>
        </Form>
      </Modal>

      {/* AI 生成 */}
      <Modal title="AI 生成巡检脚本" open={genModal} onCancel={() => { setGenModal(false); setGenResult(null) }} footer={null} width={720}>
        <Form form={genForm} layout="vertical" initialValues={{ category: 'custom' }}>
          <Form.Item name="prompt" label="用自然语言描述巡检需求" rules={[{ required: true }]}>
            <Input.TextArea rows={3} placeholder="例如：巡检一下 MySQL 主从复制状态和慢查询" />
          </Form.Item>
          <Form.Item name="category" label="巡检分类">
            <Select options={['mysql', 'redis', 'disk', 'cpu', 'memory', 'network', 'custom'].map((c) => ({ label: c, value: c }))} />
          </Form.Item>
          <Button type="primary" icon={<RobotOutlined />} onClick={doGenerate} loading={loading} block>
            生成
          </Button>
        </Form>

        {genResult && (
          <div style={{ marginTop: 16 }}>
            <Alert
              type={genResult.is_mock ? 'warning' : 'success'}
              showIcon
              message={genResult.is_mock ? '当前为 Mock 模式（未配置大模型），返回示例脚本' : '大模型生成完成'}
              description={genResult.description}
              style={{ marginBottom: 8 }}
            />
            <pre style={{ background: '#f6f8fa', padding: 12, fontSize: 12, maxHeight: 300, overflow: 'auto', border: '1px solid #eee', borderRadius: 6 }}>
              {genResult.playbook}
            </pre>
            <Button type="primary" style={{ marginTop: 8 }} onClick={saveGenerated}>
              保存为草稿模板
            </Button>
          </div>
        )}
      </Modal>
    </div>
  )
}
