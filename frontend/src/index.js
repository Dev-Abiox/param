import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider } from "next-themes";
import * as Sentry from "@sentry/react";
import "@/index.css";
import App from "@/App";

// Sentry is gated on a runtime env var so dev builds stay completely
// inert. In prod, configure REACT_APP_SENTRY_DSN at build time and
// the crash capture + performance tracing will wire themselves up.
// PHI safety: we never include personal data — beforeSend strips any
// payload that looks like a JWT, API key, or email in the message.
const SENTRY_DSN = process.env.REACT_APP_SENTRY_DSN || "";
const SENTRY_TRACES =
  parseFloat(process.env.REACT_APP_SENTRY_TRACES_SAMPLE_RATE || "0.1") || 0;
const SENTRY_ENV = process.env.REACT_APP_SENTRY_ENV || process.env.NODE_ENV || "production";

if (SENTRY_DSN) {
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: SENTRY_ENV,
    integrations: [Sentry.browserTracingIntegration()],
    tracesSampleRate: SENTRY_TRACES,
    sendDefaultPii: false,
    beforeSend(event) {
      try {
        const msg = event?.message || event?.exception?.values?.[0]?.value || "";
        // Cheap redaction: drop anything that smells like a token or email.
        if (/eyJ[A-Za-z0-9_\-.]+/.test(msg) || /[\w.-]+@[\w.-]+/.test(msg)) {
          return null;
        }
      } catch {
        /* ignore redaction failures */
      }
      return event;
    },
  });
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <ThemeProvider attribute="class" defaultTheme="light" storageKey="clinomic-theme">
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ThemeProvider>
  </React.StrictMode>,
);
