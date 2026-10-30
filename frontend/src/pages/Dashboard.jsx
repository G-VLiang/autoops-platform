import { useEffect, useMemo, useState } from 'react'
import {
  App, Badge, Button, Card, Col, Empty, Progress, Row, Segmented, Space, Statistic, Table, Tag, Tooltip,
} from 'antd'
import {
  AuditOutlined, CheckCircleOutlined, CloudServerOutlined, ReloadOutlined,
  ScheduleOutlined, ThunderboltOutlined, WarningOutlined,
} from '@ant-design/icons'
import Chart, { PALETTE } from '../components/Chart'
import { getDashboard, listReports, listTasks } from '../api/modules'

const statusColor = {
  success: 'green', failed: 'red', partial: 'orange', running: 'blue', pending: 'default',
}
const CHART_BASE = {
  textStyle: { color: '#595959', fontSize: 12 },
  grid: { left: 44, right: 16, top: 36, bottom: 28 },
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  legend: { top: 4, itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 12 } },
}
const short = (s, n = 10) => (s && s.length > n ? `${s.slice(0, n)}…` : s || '-')

export default function Dashboard() {
  const { message } = App.useApp()
  const [days, setDays] = useState(14)
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState(null)
  const [tasks, setTasks] = useState([])
  const [reports, setReports] = useState([])

  const load = async (d = days) => {
    setLoading(true)
    try {
      const [dash, t, r] = await Promise.all([
        getDashboard(d), listTasks(), listReports(),
      ])
      setData(dash.data)
      setTasks(t.data || [])
      setReports(r.data || [])
    } catch (e) {
      message.error(e?.response?.data?.detail || '看板数据加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(days) }, [days])  // eslint-disable-line react-hooks/exhaustive-deps

  const ov = data?.overview
  const trend = data?.trend?.points || []
  const hot = data?.hotspots || {}
  const dates = trend.map((p) => p.date.slice(5))

  const taskBarOption = useMemo(() => ({
    ...CHART_BASE,
    legend: { ...CHART_BASE.legend, data: ['成功', '部分成功', '失败', '成功率'] },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: '#e8e8e8' } } },
    yAxis: [
      { type: 'value', name: '任务数', splitLine: { lineStyle: { color: '#f0f0f0' } } },
      { type: 'value', name: '成功率%', max: 100, min: 0, splitLine: { show: false } },
    ],
    series: [
      { name: '成功', type: 'bar', stack: 'total', itemStyle: { color: PALETTE[1] },
        data: trend.map((p) => p.tasks.success) },
      { name: '部分成功', type: 'bar', stack: 'total', itemStyle: { color: PALETTE[2] },
        data: trend.map((p) => p.tasks.partial) },
      { name: '失败', type: 'bar', stack: 'total', itemStyle: { color: PALETTE[3] },
        data: trend.map((p) => p.tasks.failed) },
      { name: '成功率', type: 'line', yAxisIndex: 1, smooth: true, symbolSize: 5,
        connectNulls: true, itemStyle: { color: PALETTE[0] },
        data: trend.map((p) => p.task_success_rate) },
    ],
  }), [trend, dates])

  const hostOption = useMemo(() => {
    const h = ov?.hosts || { online: 0, offline: 0, unknown: 0 }
    return {
      tooltip: { trigger: 'item' },
      legend: { bottom: 0, itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 12 } },
      series: [{
        type: 'pie', radius: ['52%', '72%'], center: ['50%', '44%'],
        avoidLabelOverlap: true, label: { show: false },
        emphasis: { label: { show: true, fontSize: 16, fontWeight: 600, formatter: '{b}\n{c}' } },
        data: [
          { name: '在线', value: h.online, itemStyle: { color: PALETTE[1] } },
          { name: '离线', value: h.offline, itemStyle: { color: PALETTE[3] } },
          { name: '未知', value: h.unknown, itemStyle: { color: '#bfbfbf' } },
        ].filter((x) => x.value > 0),
      }],
    }
  }, [ov])

  const healthOption = useMemo(() => ({
    ...CHART_BASE,
    legend: { ...CHART_BASE.legend, data: ['巡检健康度', '任务成功率'] },
    xAxis: { type: 'category', boundaryGap: false, data: dates, axisLine: { lineStyle: { color: '#e8e8e8' } } },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' },
      splitLine: { lineStyle: { color: '#f0f0f0' } } },
    series: [
      { name: '巡检健康度', type: 'line', smooth: true, connectNulls: true, symbolSize: 5,
        itemStyle: { color: PALETTE[5] },
        areaStyle: { color: 'rgba(19,194,194,0.12)' },
        data: trend.map((p) => p.report_health) },
      { name: '任务成功率', type: 'line', smooth: true, connectNulls: true, symbolSize: 5,
        itemStyle: { color: PALETTE[0] },
        data: trend.map((p) => p.task_success_rate) },
    ],
  }), [trend, dates])

  const failedHostOption = useMemo(() => {
    const rows = [...(hot.failed_hosts || [])].reverse()
    return {
      ...CHART_BASE,
      grid: { left: 90, right: 40, top: 16, bottom: 24 },
      xAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f0f0' } } },
      yAxis: { type: 'category', data: rows.map((r) => short(r.host, 12)),
        axisLine: { lineStyle: { color: '#e8e8e8' } } },
      series: [{
        type: 'bar', barMaxWidth: 18, itemStyle: { color: PALETTE[3], borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: 'right', fontSize: 11 },
        data: rows.map((r) => r.count),
      }],
    }
  }, [hot])

  const templateOption = useMemo(() => {
    const rows = hot.failing_templates || []
    return {
      ...CHART_BASE,
      grid: { left: 44, right: 16, top: 16, bottom: 46 },
      xAxis: { type: 'category', data: rows.map((r) => short(r.template, 8)),
        axisLabel: { interval: 0, rotate: rows.length > 4 ? 20 : 0 } },
      yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' },
        splitLine: { lineStyle: { color: '#f0f0f0' } } },
      series: [{
        type: 'bar', barMaxWidth: 28,
        itemStyle: { color: (p) => (p.value >= 50 ? PALETTE[3] : p.value >= 20 ? PALETTE[2] : PALETTE[1]),
          borderRadius: [4, 4, 0, 0] },
        label: { show: true, position: 'top', formatter: '{c}%', fontSize: 11 },
        data: rows.map((r) => r.fail_rate),
      }],
    }
  }, [hot])

  const categoryOption = useMemo(() => ({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 12 } },
    series: [{
      type: 'pie', radius: '62%', center: ['50%', '44%'],
      label: { formatter: '{b} {c}', fontSize: 11 },
      data: (hot.categories || []).map((c, i) => ({
        ...c, itemStyle: { color: PALETTE[i % PALETTE.length] },
      })),
    }],
  }), [hot])

  const kpis = [
    { title: '主机总数', value: ov?.hosts.total ?? '-', icon: <CloudServerOutlined />,
      extra: <span style={{ color: '#8c8c8c', fontSize: 12 }}>在线率 {ov?.hosts.online_rate ?? 0}%</span> },
    { title: '任务总数', value: ov?.tasks.total ?? '-', icon: <ThunderboltOutlined />,
      extra: <span style={{ color: '#8c8c8c', fontSize: 12 }}>成功 {ov?.tasks.by_status.success ?? 0}</span> },
    { title: '任务成功率', value: ov?.tasks.success_rate ?? 0, suffix: '%', icon: <CheckCircleOutlined />,
      extra: <span style={{ color: '#8c8c8c', fontSize: 12 }}>失败 {ov?.tasks.by_status.failed ?? 0}</span> },
    { title: '巡检健康度', value: ov?.reports.health_7d ?? '-', suffix: ov?.reports.health_7d != null ? '%' : '',
      icon: <AuditOutlined />,
      extra: <span style={{ color: '#8c8c8c', fontSize: 12 }}>近 7 天 {ov?.reports.total ?? 0} 份报告</span> },
    { title: '启用计划', value: ov?.catalog.plans_enabled ?? '-', icon: <ScheduleOutlined />,
      extra: <span style={{ color: '#8c8c8c', fontSize: 12 }}>共 {ov?.catalog.plans ?? 0} 个</span> },
    { title: '告警渠道', value: ov?.catalog.alerts ?? '-', icon: <WarningOutlined />,
      extra: <span style={{ color: '#8c8c8c', fontSize: 12 }}>
        凭据 {ov?.catalog.credentials ?? 0} · 模板 {ov?.catalog.templates ?? 0}</span> },
  ]

  return (
    <div>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Space>
          <Segmented value={days} onChange={setDays}
            options={[{ label: '近 7 天', value: 7 }, { label: '近 14 天', value: 14 }, { label: '近 30 天', value: 30 }]} />
          {data?.generated_at && (
            <span style={{ color: '#bfbfbf', fontSize: 12 }}>
              生成于 {new Date(data.generated_at).toLocaleTimeString()}
            </span>
          )}
        </Space>
        <Space>
          {ov?.tenants_total != null && <Tag color="purple">平台租户 {ov.tenants_total}</Tag>}
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => load(days)}>刷新</Button>
        </Space>
      </Space>

      <Row gutter={[16, 16]}>
        {kpis.map((k) => (
          <Col xs={24} sm={12} md={8} xl={4} key={k.title}>
            <Card size="small" loading={loading && !data}>
              <Statistic title={<Space size={4}>{k.icon}{k.title}</Space>} value={k.value} suffix={k.suffix} />
              <div style={{ marginTop: 4 }}>{k.extra}</div>
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} xl={16}>
          <Card size="small" title="任务执行结果（按天）" extra={<Tag>成功 / 部分成功 / 失败 + 成功率</Tag>}>
            <Chart option={taskBarOption} height={300} />
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card size="small" title="主机状态分布"
            extra={<Badge color={ov?.hosts.offline ? 'red' : 'green'} text={`${ov?.hosts.total ?? 0} 台`} />}>
            {ov?.hosts.total ? <Chart option={hostOption} height={300} /> : <Empty style={{ padding: 60 }} />}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} xl={12}>
          <Card size="small" title="巡检健康度 vs 任务成功率">
            <Chart option={healthOption} height={280} />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card size="small" title={`失败/不可达 Top 主机（近 ${hot.days ?? 30} 天）`}>
            {(hot.failed_hosts || []).length
              ? <Chart option={failedHostOption} height={280} />
              : <Empty description="窗口期内没有失败记录" style={{ padding: 60 }} />}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} xl={12}>
          <Card size="small" title={`模板失败率（近 ${hot.days ?? 30} 天执行过的模板）`}>
            {(hot.failing_templates || []).length
              ? <Chart option={templateOption} height={240} />
              : <Empty description="暂无巡检数据" style={{ padding: 40 }} />}
          </Card>
        </Col>
        <Col xs={24} xl={6}>
          <Card size="small" title="模板分类">
            {(hot.categories || []).length
              ? <Chart option={categoryOption} height={240} />
              : <Empty style={{ padding: 40 }} />}
          </Card>
        </Col>
        <Col xs={24} xl={6}>
          <Card size="small" title="任务类型占比">
            <Space direction="vertical" style={{ width: '100%', padding: '8px 4px' }} size={12}>
              {(hot.task_types || []).map((t, i) => {
                const total = (hot.task_types || []).reduce((a, b) => a + b.value, 0) || 1
                return (
                  <div key={t.name}>
                    <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                      <Tag color={PALETTE[i % PALETTE.length]}>{t.name}</Tag>
                      <span style={{ color: '#8c8c8c', fontSize: 12 }}>
                        {t.value} 次 · {Math.round((t.value / total) * 100)}%
                      </span>
                    </Space>
                    <Progress percent={Math.round((t.value / total) * 100)} showInfo={false}
                      size="small" strokeColor={PALETTE[i % PALETTE.length]} />
                  </div>
                )
              })}
              {!(hot.task_types || []).length && <Empty style={{ padding: 30 }} />}
            </Space>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} xl={12}>
          <Card size="small" title="最近任务" extra={<span style={{ color: '#bfbfbf', fontSize: 12 }}>最近 6 条</span>}>
            <Table
              rowKey="id" size="small" pagination={false}
              dataSource={tasks.slice(0, 6)}
              columns={[
                { title: '名称', dataIndex: 'name', ellipsis: true,
                  render: (v, r) => <Tooltip title={r.content || ''}>{v}</Tooltip> },
                { title: '类型', dataIndex: 'task_type', width: 90, render: (v) => <Tag>{v}</Tag> },
                { title: '状态', dataIndex: 'status', width: 90,
                  render: (v) => <Tag color={statusColor[v]}>{v}</Tag> },
                { title: '结果', dataIndex: 'summary', width: 170,
                  render: (s) => (s ? <Space size={2} wrap>
                    {Object.entries(s).map(([k, v]) => <Tag key={k} style={{ marginInlineEnd: 0 }}>{k}:{v}</Tag>)}
                  </Space> : '-') },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card size="small" title="最近巡检报告"
            extra={<span style={{ color: '#bfbfbf', fontSize: 12 }}>最近 6 条</span>}>
            <Table
              rowKey="id" size="small" pagination={false}
              dataSource={reports.slice(0, 6)}
              columns={[
                { title: '计划', dataIndex: 'plan_name', ellipsis: true },
                { title: '模板', dataIndex: 'template_name', ellipsis: true },
                { title: '状态', dataIndex: 'status', width: 90,
                  render: (v) => <Tag color={statusColor[v]}>{v}</Tag> },
                { title: '时间', dataIndex: 'created_at', width: 160,
                  render: (v) => (v ? new Date(v).toLocaleString() : '-') },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  )
}
