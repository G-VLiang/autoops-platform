import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { LineChart, BarChart, PieChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent, TitleComponent, DatasetComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart, BarChart, PieChart,
  GridComponent, TooltipComponent, LegendComponent, TitleComponent, DatasetComponent,
  CanvasRenderer,
])

// 主题色：与 AntD 默认色板对齐，保持看板整体一致
export const PALETTE = ['#1677ff', '#52c41a', '#faad14', '#ff4d4f', '#722ed1', '#13c2c2']

export default function Chart({ option, height = 280, onEvents }) {
  const el = useRef(null)
  const inst = useRef(null)

  useEffect(() => {
    if (!el.current) return undefined
    inst.current = echarts.init(el.current, null, { renderer: 'canvas' })
    const resize = () => inst.current && inst.current.resize()
    window.addEventListener('resize', resize)
    return () => {
      window.removeEventListener('resize', resize)
      if (inst.current) {
        inst.current.dispose()
        inst.current = null
      }
    }
  }, [])

  useEffect(() => {
    if (inst.current && option) inst.current.setOption(option, true)
  }, [option])

  useEffect(() => {
    if (!inst.current || !onEvents) return undefined
    Object.entries(onEvents).forEach(([evt, handler]) => inst.current.on(evt, handler))
    return () => {
      Object.keys(onEvents).forEach((evt) => inst.current && inst.current.off(evt))
    }
  }, [onEvents])

  return <div ref={el} style={{ width: '100%', height }} />
}
