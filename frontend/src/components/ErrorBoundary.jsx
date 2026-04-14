import React from 'react';
import * as Sentry from '@sentry/react';

// Persists across the auto-reload via sessionStorage. Allows ONE silent retry
// (a transient error like a chunk-load failure usually clears) and then
// shows a hard-error screen instead of looping forever.
const RELOAD_KEY = 'eb_reload_count';
const MAX_AUTO_RELOADS = 1;

const getReloadCount = () => {
  try {
    return parseInt(sessionStorage.getItem(RELOAD_KEY) || '0', 10);
  } catch {
    return 0;
  }
};

const incrementReloadCount = () => {
  try {
    sessionStorage.setItem(RELOAD_KEY, String(getReloadCount() + 1));
  } catch {}
};

const resetReloadCount = () => {
  try {
    sessionStorage.removeItem(RELOAD_KEY);
  } catch {}
};

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, reloadCount: getReloadCount() };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo);
    // Forward to Sentry if it's been initialised (gated on DSN). Safe to
    // call unconditionally — when Sentry.init() wasn't run, captureException
    // is a no-op client that drops the event.
    try {
      Sentry.captureException(error, { contexts: { react: { componentStack: errorInfo?.componentStack } } });
    } catch { /* never let the error reporter break the error boundary */ }
  }

  componentDidMount() {
    // If we successfully mounted (no error), reset the counter so a future
    // unrelated error gets a fresh retry budget.
    if (!this.state.hasError) {
      resetReloadCount();
    }
  }

  handleReload = () => {
    incrementReloadCount();
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      const exhausted = this.state.reloadCount >= MAX_AUTO_RELOADS;
      return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50">
          <div className="text-center p-8 max-w-md">
            <h2 className="text-xl font-semibold text-red-600 mb-2">
              {exhausted ? "We can't recover from this error" : "Something went wrong"}
            </h2>
            <p className="text-slate-600 mb-4">
              {exhausted
                ? "Reloading didn't help. Please contact support and include any actions you took before this screen appeared."
                : "An unexpected error occurred. Try refreshing the page once."}
            </p>
            {!exhausted && (
              <button
                onClick={this.handleReload}
                className="px-4 py-2 bg-teal-600 text-white rounded-md hover:bg-teal-700 transition-colors mr-2"
              >
                Refresh Page
              </button>
            )}
            <button
              onClick={() => {
                resetReloadCount();
                this.setState({ hasError: false, error: null, reloadCount: 0 });
              }}
              className="px-4 py-2 bg-slate-200 text-slate-700 rounded-md hover:bg-slate-300 transition-colors"
            >
              {exhausted ? "Try again anyway" : "Dismiss"}
            </button>
            {this.state.error?.message && (
              <p className="mt-4 text-xs text-slate-400 break-all">
                {String(this.state.error.message).slice(0, 200)}
              </p>
            )}
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
