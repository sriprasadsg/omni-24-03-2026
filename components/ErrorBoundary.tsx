import React, { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
    children: ReactNode;
    fallback?: ReactNode;
    name?: string;
}

interface State {
    hasError: boolean;
    error: Error | null;
}

// A tab that outlives a dev-server restart (or a deploy) can lazy-load a view
// that imports a second, never-rendered copy of React, whose null hook
// dispatcher throws on the first hook call (Chrome / Firefox / Safari wording).
const STALE_REACT_ERROR = /Cannot read properties of null \(reading 'use\w+'\)|can't access property "use\w+", \w+ is null|null is not an object \(evaluating '\w+\.use\w+'\)/;
const RELOAD_KEY = 'errorBoundary:staleReactReloadAt';
const RELOAD_WINDOW_MS = 30_000;

// Reload at most once per window so a genuine bug can't cause a reload loop.
// Without sessionStorage we can't enforce that, so we don't reload at all.
function reloadOnceForStaleReact(error: Error): boolean {
    if (!STALE_REACT_ERROR.test(error.message)) return false;
    try {
        const last = Number(sessionStorage.getItem(RELOAD_KEY));
        if (last && Date.now() - last < RELOAD_WINDOW_MS) return false;
        sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
    } catch {
        return false;
    }
    window.location.reload();
    return true;
}

export class ErrorBoundary extends Component<Props, State> {
    public state: State = {
        hasError: false,
        error: null
    };

    public static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
        if (reloadOnceForStaleReact(error)) return;
        if (import.meta.env.DEV) {
            console.error(`Uncaught error in ${this.props.name || 'Component'}:`, error, errorInfo);
        }
    }

    public render() {
        if (this.state.hasError) {
            if (this.props.fallback) {
                return this.props.fallback;
            }
            return (
                <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-800">
                    <h3 className="font-bold text-lg mb-2">Something went wrong</h3>
                    <p className="text-sm">{this.state.error?.message}</p>
                    <button
                        className="mt-4 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
                        onClick={() => this.setState({ hasError: false, error: null })}
                    >
                        Try Again
                    </button>
                </div>
            );
        }

        return this.props.children;
    }
}
