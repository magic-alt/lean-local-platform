import { Alert, Button } from "antd";
import { Component, type ErrorInfo, type ReactNode } from "react";

interface RunDetailPanelBoundaryProps {
  children: ReactNode;
  panel: string;
  resetKey: string;
}

interface RunDetailPanelBoundaryState {
  error?: Error;
}

export class RunDetailPanelBoundary extends Component<
  RunDetailPanelBoundaryProps,
  RunDetailPanelBoundaryState
> {
  state: RunDetailPanelBoundaryState = {};

  static getDerivedStateFromError(error: Error): RunDetailPanelBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`Backtest ${this.props.panel} panel failed to render`, error, info);
  }

  componentDidUpdate(previousProps: RunDetailPanelBoundaryProps) {
    if (previousProps.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: undefined });
    }
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <Alert
        type="error"
        showIcon
        message={`${this.props.panel} could not be displayed.`}
        description="The report contains a value this panel could not render. Other report tabs remain available."
        action={<Button size="small" onClick={() => this.setState({ error: undefined })}>Retry</Button>}
      />
    );
  }
}
