import { Component, type ReactNode } from "react"

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

// A crash inside any one chart (e.g. a charting library rejecting a bad
// data point) must not blank the entire Performance page — every chart
// lives inside its own boundary so the rest of the page keeps rendering.
export class ChartErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <p className="text-sm text-[var(--status-critical)]">
          Couldn't render this chart: {this.state.error.message}
        </p>
      )
    }
    return this.props.children
  }
}
