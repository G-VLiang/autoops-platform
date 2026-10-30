import { useEffect, useState } from 'react'
import {
  Alert, Button, Card, Descriptions, Drawer, Form, Input, Modal, Popconfirm, Select, Space,
  Switch, Table, Tabs, Tag, message,
} from 'antd'
import {
  BellOutlined, DownloadOutlined, FileExcelOutlined, FilePdfOutlined, PlusOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons'
import { Link } from 'react-router-dom'
import {
  listPlans, createPlan, updatePlan, deletePlan, runPlan,
  listTemplates, listGroups, listHosts, listReports, reportExportUrl, reportsExportAllUrl,
} from '../api/modules'
import { download } from '../api/index'
import CronBuilder from '../components/CronBuilder'

const statusColor = { success: 'green', failed: 'red', partial: 'orange' }
const statusLabel = { success: '成功', failed: '失败', partial: '部分失败' }

export default function InspectionPlans() {
  const [plans, setPlans] = useState([])
  const [templates, setTemplates] = useState([])
  const [groups, setGroups] = useState([])
  const [hosts, setHosts] = useState([])
  const [reports, setReports] = useState([])
  const [planModal, setPlanModal] = useState(false)
  const [reportDrawer, setReportDrawer] = useState(null)
  const [busy, setBusy] = useState('')
  const [form] = Form.useForm()

  const load = () => {
    listPlans().then((r) => setPlans(r.data)).catch(() => {})
    listTemplates().then((r) => setTemplates(r.data)).catch(() => {})
    listGroups().then((r) => setGroups(r.data)).catch(() => {})
    listHosts().then((r) => setHosts(r.data)).catch(() => {})
    listReports().then((r) => setReports(r.data)).catch(() => {})
  }

  useEffect(load, [])

  const submitPlan = async () => {
    const values = await form.validateFields()
    try {
      await createPlan(values)
      message.success('计划已创建')
      setPlanModal(false)
      form.resetFields()
      load()
    } catch (e) {
      message.error(e?.response?.data?.detail || '创建失败')
    }
  }

  const doRun = async (plan) => {
    setBusy(plan.id)
    try {
      await runPlan(plan.id)
      message.success('巡检已执行')
      load()
    } catch (e) {
      message.error(e?.response?.data?.detail || '执行失败')
    } finally {
      setBusy('')
    }
  }

  const toggleEnabled = async (plan, checked) => {
    await updatePlan(plan.id, {
      name: plan.name, template_id: plan.template_id, target_type: plan.target_type,
      target_id: plan.target_id, cron: plan.cron, enabled: checked,
    })
    load()
  }

  const exportReport = async (report, format) => {
    setBusy(`exp-${report.id}-${format}`)
    try {
      await download(
        reportExportUrl(report.id, format),
        `巡检报告-${report.plan_name}.${format}`,
      )
      message.success(`已导出 ${format.toUpperCase()}`)
    } catch (e) {
      const detail = e?.response?.data?.detail
      message.error(detail || '导出失败')
    } finally {
      setBusy('')
    }
  }

  const exportAll = async () => {
    setBusy('exp-all')
    try {
      await download(reportsExportAllUrl(30), '巡检报告汇总-近30天.xlsx')
      message.success('汇总表已导出')
    } catch (e) {
      message.error(e?.response?.data?.detail || '导出失败')
    } finally {
      setBusy('')
    }
  }

  const planColumns = [
    { title: '名称', dataIndex: 'name' },
    { title: '巡检模板', dataIndex: 'template_name', render: (v) => v || '-' },
    { title: '调度', dataIndex: 'cron', render: (v) => <Tag color="blue">{v}</Tag> },
    {
      title: '启用', dataIndex: 'enabled',
      render: (v, r) => <Switch size="small" checked={v} onChange={(c) => toggleEnabled(r, c)} />,
    },
    { title: '上次执行', dataIndex: 'last_run_at', render: (v) => (v ? new Date(v).toLocaleString() : '-') },
    {
      title: '操作', width: 180, render: (_, r) => (
        <Space size={0}>
          <Button type="link" size="small" icon={<PlayCircleOutlined />}
            loading={busy === r.id} onClick={() => doRun(r)}>立即执行</Button>
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
    {
      title: '状态', dataIndex: 'status',
      render: (v) => <Tag color={statusColor[v]}>{statusLabel[v] || v}</Tag>,
    },
    {
      title: '结果', dataIndex: 'summary',
      render: (s) => (
        <Space size={4}>
          {Object.entries(s || {}).map(([k, v]) => <Tag key={k}>{k}:{v}</Tag>)}
        </Space>
      ),
    },
    { title: '时间', dataIndex: 'created_at', width: 175, render: (v) => new Date(v).toLocaleString() },
    {
      title: '操作', width: 220, render: (_, r) => (
        <Space size={0}>
          <Button type="link" size="small" onClick={() => setReportDrawer(r)}>详情</Button>
          <Button type="link" size="small" icon={<FilePdfOutlined />}
            loading={busy === `exp-${r.id}-pdf`}
            onClick={() => exportReport(r, 'pdf')}>PDF</Button>
          <Button type="link" size="small" icon={<FileExcelOutlined />}
            loading={busy === `exp-${r.id}-xlsx`}
            onClick={() => exportReport(r, 'xlsx')}>Excel</Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Card
        title="巡检计划"
        extra={
          <Space>
            <Button icon={<DownloadOutlined />} loading={busy === 'exp-all'} onClick={exportAll}>
              导出近 30 天汇总
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setPlanModal(true)}>
              新建计划
            </Button>
          </Space>
        }
      >
        <Tabs
          items={[
            {
              key: 'plans', label: '巡检计划',
              children: <Table rowKey="id" dataSource={plans} columns={planColumns} />,
            },
            {
              key: 'reports', label: '巡检报告',
              children: <Table rowKey="id" dataSource={reports} columns={reportColumns} />,
            },
            {
              key: 'alerts', label: <span><BellOutlined /> 告警</span>,
              children: (
                <Alert
                  type="info" showIcon
                  message="告警配置已整合到「告警中心」"
                  description={(
                    <span>
                      现在支持告警分级（严重/警告/提示）、按级别路由不同渠道、未恢复去重、
                      恢复通知与维护期静默。入口：左侧菜单 <Link to="/alerts">告警中心</Link>。
                    </span>
                  )}
                />
              ),
            },
          ]}
        />
      </Card>

      <Modal title="新建巡检计划" open={planModal} onOk={submitPlan}
        onCancel={() => setPlanModal(false)} width={620}>
        <Form form={form} layout="vertical"
          initialValues={{ target_type: 'group', cron: '0 2 * * *', enabled: true }}>
          <Form.Item name="name" label="计划名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="template_id" label="巡检模板" rules={[{ required: true }]}>
            <Select options={templates.map((t) => ({ label: t.name, value: t.id }))} />
          </Form.Item>
          <Form.Item name="target_type" label="目标类型">
            <Select options={[{ label: '主机组', value: 'group' }, { label: '单台主机', value: 'host' }]} />
          </Form.Item>
          <Form.Item name="target_id" label="目标" rules={[{ required: true }]}>
            <Select
              showSearch optionFilterProp="label"
              options={[
                ...groups.map((g) => ({ label: `[组] ${g.name}`, value: g.id })),
                ...hosts.map((h) => ({ label: `[主机] ${h.hostname}`, value: h.id })),
              ]}
            />
          </Form.Item>
          <Form.Item name="cron" label="调度周期" rules={[{ required: true }]}
            extra="可视化选择或直接写 cron 表达式，下方会显示接下来几次执行时间">
            <CronBuilder />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={reportDrawer ? `巡检报告 - ${reportDrawer.plan_name}` : '巡检报告'}
        open={!!reportDrawer} onClose={() => setReportDrawer(null)} width={620}
        extra={reportDrawer && (
          <Space>
            <Button icon={<FilePdfOutlined />} onClick={() => exportReport(reportDrawer, 'pdf')}>PDF</Button>
            <Button icon={<FileExcelOutlined />} onClick={() => exportReport(reportDrawer, 'xlsx')}>Excel</Button>
          </Space>
        )}
      >
        {reportDrawer && (
          <>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="计划">{reportDrawer.plan_name}</Descriptions.Item>
              <Descriptions.Item label="模板">{reportDrawer.template_name}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusColor[reportDrawer.status]}>
                  {statusLabel[reportDrawer.status] || reportDrawer.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="结果">
                {Object.entries(reportDrawer.summary || {}).map(([k, v]) => (
                  <Tag key={k}>{k}:{v}</Tag>
                ))}
              </Descriptions.Item>
              <Descriptions.Item label="执行时间">
                {new Date(reportDrawer.created_at).toLocaleString()}
              </Descriptions.Item>
            </Descriptions>
            {reportDrawer.content && (
              <pre style={{
                background: '#f6f8fa', padding: 12, borderRadius: 6, marginTop: 16,
                fontSize: 12, whiteSpace: 'pre-wrap',
              }}>{reportDrawer.content}</pre>
            )}
          </>
        )}
      </Drawer>
    </div>
  )
}
