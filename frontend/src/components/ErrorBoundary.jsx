import { Component } from 'react'
import { Button, Result, Typography } from 'antd'

const { Paragraph, Text } = Typography

/**
 * 异常边界：单个页面渲染出错时只挂掉该区域，导航与其余页面仍可用。
 * 不做全局白屏，也把错误信息折叠起来方便反馈问题。
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // 保留控制台堆栈，便于排查；生产环境可在此上报
    console.error('[页面异常]', error, info?.componentStack)
  }

  reset = () => this.setState({ error: null })

  render() {
    const { error } = this.state
    if (!error) return this.props.children
    return (
      <Result
        status="warning"
        title="页面加载出错了"
        subTitle="当前页面渲染时发生异常，其他功能仍可正常使用。可以重试，或刷新页面。"
        extra={[
          <Button type="primary" key="retry" onClick={this.reset}>重试</Button>,
          <Button key="reload" onClick={() => window.location.reload()}>刷新页面</Button>,
        ]}
      >
        <Paragraph>
          <Text type="secondary">错误信息：</Text>
        </Paragraph>
        <Paragraph>
          <Text code style={{ whiteSpace: 'pre-wrap' }}>
            {String(error?.message || error)}
          </Text>
        </Paragraph>
      </Result>
    )
  }
}
