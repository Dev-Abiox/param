import React from "react";
import { Navigate } from "react-router-dom";
import * as Sentry from "@sentry/react";

import { getDefaultRoute } from "@/lib/routing";

// Small "something broke in this view" fallback so a render error
// in one route doesn't take down the whole shell. Purposely minimal
// so it can't itself crash.
const RouteErrorFallback = ({ resetError }) => (
  <div className="flex items-center justify-center p-8">
    <div className="max-w-md rounded-md border border-red-200 bg-red-50 p-6 text-center">
      <h3 className="mb-2 text-base font-semibold text-red-700">
        This page hit an unexpected error
      </h3>
      <p className="mb-4 text-sm text-red-600">
        The rest of the app is still working — try again, or navigate to
        another section.
      </p>
      <button
        onClick={() => {
          try { resetError && resetError(); } catch { /* noop */ }
        }}
        className="rounded bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-700"
      >
        Retry
      </button>
    </div>
  </div>
);

/**
 * Protected
 *
 * Wraps a route's element with:
 *   1. a role / permission guard that redirects unauthorised users to
 *      their role's default route, and
 *   2. a Sentry error boundary so a render error in one lazy chunk
 *      doesn't propagate to the app shell. Sentry.ErrorBoundary is
 *      a no-op reporter if Sentry.init() was never called, so this
 *      is safe in dev.
 *
 * Usage:
 *   <Route path="/dashboard" element={
 *     <Protected allowed={isSuperAdmin(user)} role={user.role}>
 *       <AdminDashboard />
 *     </Protected>
 *   } />
 */
const Protected = ({ allowed, role, children }) => {
  if (!allowed) {
    return <Navigate to={getDefaultRoute(role)} replace />;
  }
  return (
    <Sentry.ErrorBoundary fallback={RouteErrorFallback}>
      {children}
    </Sentry.ErrorBoundary>
  );
};

export default Protected;
export { RouteErrorFallback };
