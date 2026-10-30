import { useEffect, useState } from 'react'
import { Alert, Input, Select, Space, Tag, TimePicker, Typography } from 'antd'
import dayjs from 'dayjs'
import { previewCron } from '../api/modules'

const { Text } = Typography

const MODES = [
  { label: '每天', value: 'daily' },
  { label: '每小时', value: 'hourly' },
  { label: '每周', value: 'weekly' },
  { label: '每月', value: 'monthly' },
  { label: '自定义', value: 'custom' },
]

const WEEKDAYS = [
  { label: '周一', value: '1' }, { label: '周二', value: '2' }, { label: '周三', value: '3' },
  { label: '周四', value: '4' }, { label: '周五', value: '5' }, { label: '周六', value: '6' },
  { label: '周日', value: '0' },
]

/** 把 cron 表达式解析成可视化控件状态；解析不出来就落到自定义模式。 */
function parse(expr) {
  const parts = (expr || '').trim().split(/\s+/)
  if (parts.length !== 5) return { mode: 'custom', expr }
  const [mi, ho, dom, mon, dow] = parts
  if (mi === '*' && ho === '*') return { mode: 'hourly', minute: 0 }
  if (/^\d+$/.test(mi) && /^\d+$/.test(ho) && dom === '*' && mon === '*' && dow === '*') {
    return { mode: 'daily', time: `${ho.padStart(2, '0')}:${mi.padStart(2, '0')}` }
  }
  if (/^\d+$/.test(mi) && /^\d+$/.test(ho) && dom === '*' && mon === '*' && /^\d$/.test(dow)) {
    return { mode: 'weekly', time: `${ho.padStart(2, '0')}:${mi.padStart(2, '0')}`, weekday: dow }
  }
  if (/^\d+$/.test(mi) && /^\d+$/.test(ho) && /^\d+$/.test(dom) && mon === '*' && dow === '*') {
    return { mode: 'monthly', time: `${ho.padStart(2, '0')}:${mi.padStart(2, '0')}`, day: Number(dom) }
  }
  return { mode: 'custom', expr }
}

function compose({ mode, time = '02:00', minute = 0, weekday = '1', day = 1 }) {
  const [h, m] = (time || '02:00').split(':').map(Number)
  switch (mode) {
    case 'hourly': return `${minute} * * * *`
    case 'daily': return `${m} ${h} * * *`
    case 'weekly': return `${m} ${h} * * ${weekday}`
    case 'monthly': return `${m} ${h} ${day} * *`
    default: return ''
  }
}

/**
 * cron 可视化编辑器：控件组合出表达式，并实时向服务端要「下次执行时间」。
 * value / onChange 与 Form.Item 无缝对接（值为字符串表达式）。
 */
export default function CronBuilder({ value, onChange }) {
  const initial = parse(value)
  const [state, setState] = useState(initial)
  const [preview, setPreview] = useState(null)

  // 外部值变化（如编辑已有计划）时同步控件
  useEffect(() => {
    const parsed = parse(value)
    setState((prev) => (prev.mode === parsed.mode && prev.expr === parsed.expr ? prev : parsed))
  }, [value])

  const update = (patch) => {
    const next = { ...state, ...patch }
    setState(next)
    if (next.mode !== 'custom') {
      const expr = compose(next)
      if (expr) onChange?.(expr)
    }
  }

  const expr = state.mode === 'custom' ? (state.expr || '') : compose(state)

  // 表达式变化后请求下次执行时间
  useEffect(() => {
    if (!expr) { setPreview(null); return }
    let alive = true
    const timer = setTimeout(() => {
      previewCron(expr, 4)
        .then((r) => { if (alive) setPreview(r.data) })
        .catch(() => { if (alive) setPreview(null) })
    }, 300)
    return () => { alive = false; clearTimeout(timer) }
  }, [expr])

  return (
    <div>
      <Space wrap style={{ marginBottom: 8 }}>
        <Select value={state.mode} style={{ width: 110 }}
          onChange={(mode) => {
            const patch = { mode }
            if (mode === 'custom') patch.expr = expr || '0 2 * * *'
            update(patch)
          }}
          options={MODES} />

        {state.mode === 'hourly' && (
          <span>
            第 <Input style={{ width: 70, display: 'inline-block' }} type="number" min={0} max={59}
              value={state.minute}
              onChange={(e) => update({ minute: Number(e.target.value) || 0 })} /> 分钟
          </span>
        )}

        {(state.mode === 'daily' || state.mode === 'weekly' || state.mode === 'monthly') && (
          <TimePicker
            format="HH:mm" allowClear={false}
            value={dayjs(state.time || '02:00', 'HH:mm')}
            onChange={(v) => update({ time: v ? v.format('HH:mm') : '02:00' })}
          />
        )}

        {state.mode === 'weekly' && (
          <Select value={state.weekday} style={{ width: 100 }}
            onChange={(v) => update({ weekday: v })} options={WEEKDAYS} />
        )}

        {state.mode === 'monthly' && (
          <span>
            每月第 <Input style={{ width: 70, display: 'inline-block' }} type="number" min={1} max={28}
              value={state.day}
              onChange={(e) => update({ day: Math.min(28, Math.max(1, Number(e.target.value) || 1)) })} /> 天
          </span>
        )}

        {state.mode === 'custom' && (
          <Input style={{ width: 200 }} value={state.expr}
            placeholder="分 时 日 月 周，如 0 2 * * *"
            onChange={(e) => { setState({ ...state, expr: e.target.value }); onChange?.(e.target.value) }} />
        )}
      </Space>

      <div style={{ fontSize: 12 }}>
        <Text type="secondary">表达式：</Text>
        <Tag color="blue">{expr || '-'}</Tag>
        {preview?.description && <Text type="secondary">{preview.description}</Text>}
      </div>

      {preview && !preview.valid && (
        <Alert type="error" showIcon style={{ marginTop: 8 }}
          message={`表达式无效：${preview.error}`} />
      )}
      {preview?.valid && preview.next_runs?.length > 0 && (
        <div style={{ marginTop: 6, fontSize: 12, color: '#8c8c8c' }}>
          接下来执行：
          {preview.next_runs.map((t) => (
            <Tag key={t} style={{ marginLeft: 4 }}>{dayjs(t).format('MM-DD HH:mm')}</Tag>
          ))}
        </div>
      )}
    </div>
  )
}
