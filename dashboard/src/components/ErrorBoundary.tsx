import { Component, ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info.componentStack);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-[400px] items-center justify-center rounded-xl border border-[#ff4d6a40] bg-[#1a1a2e] p-8">
          <div className="text-center">
            <h2 className="mb-2 text-lg font-semibold text-[#e8e8f0]">
              Something went wrong
            </h2>
            <p className="mb-4 text-sm text-[#8888a0]">
              {this.state.error?.message || "An unexpected error occurred"}
            </p>
            <button
              onClick={this.handleReload}
              className="rounded-lg bg-[#4d8eff] px-4 py-2 text-sm font-medium text-white hover:bg-[#4d8eff]/80"
            >
              Reload Dashboard
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
