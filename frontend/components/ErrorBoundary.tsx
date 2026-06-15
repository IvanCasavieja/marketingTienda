"use client";
import { Component, ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (this.state.error) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="flex flex-col items-center justify-center min-h-[40vh] gap-4 text-center px-4">
          <div className="w-14 h-14 rounded-2xl bg-red-50 flex items-center justify-center">
            <AlertTriangle size={24} className="text-red-500" />
          </div>
          <div>
            <p className="font-semibold text-slate-800">Algo salió mal</p>
            <p className="text-sm text-slate-500 mt-1 max-w-sm">
              {this.state.error.message || "Error inesperado en la aplicación"}
            </p>
          </div>
          <button
            onClick={() => this.setState({ error: null })}
            className="flex items-center gap-2 text-sm font-medium text-brand-600 hover:text-brand-700 border border-brand-200 hover:border-brand-300 px-4 py-2 rounded-lg transition-colors"
          >
            <RefreshCw size={14} />
            Reintentar
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
