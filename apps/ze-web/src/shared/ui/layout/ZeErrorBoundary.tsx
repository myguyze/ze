import { Component, type ErrorInfo, type ReactNode } from "react";
import { ZeErrorFallback } from "./ZeErrorFallback";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ZeErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ZeErrorBoundary]", error, info.componentStack);
  }

  private handleReset = () => {
    this.setState({ error: null });
  };

  render() {
    if (this.state.error) {
      return <ZeErrorFallback error={this.state.error} onReset={this.handleReset} />;
    }
    return this.props.children;
  }
}
