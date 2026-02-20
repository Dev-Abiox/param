import { useEffect, useRef, useCallback, useState } from "react";

const RECONNECT_BASE_MS = 1000;
const RECONNECT_CAP_MS = 30000;
const MAX_RECONNECT_ATTEMPTS = 10;

/**
 * Custom hook for WebSocket connections with first-message auth.
 *
 * Protocol:
 *   1. Opens ws://host/ws/queue/ (no token in URL)
 *   2. On open, sends {"type": "auth", "token": "<JWT>"}
 *   3. Waits for {"type": "auth_ok"} before forwarding messages
 *
 * @param {string}   path       - WebSocket path (e.g. "/ws/queue/")
 * @param {Function} onMessage  - Callback invoked with parsed JSON messages
 * @param {Object}   opts
 * @param {boolean}  opts.enabled - Whether the connection should be active (default true)
 * @param {string}   opts.token   - JWT access token for authentication
 * @returns {{ connected: boolean, reconnecting: boolean }}
 */
export default function useWebSocket(path, onMessage, { enabled = true, token } = {}) {
  const [connected, setConnected] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);

  const wsRef = useRef(null);
  const attemptRef = useRef(0);
  const timerRef = useRef(null);
  const onMessageRef = useRef(onMessage);
  const authedRef = useRef(false);
  const prevTokenRef = useRef(null);
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    if (!enabled || !token) return;

    // Skip reconnect if the token hasn't actually changed and we're already connected
    if (token === prevTokenRef.current && wsRef.current?.readyState === WebSocket.OPEN) return;
    prevTokenRef.current = token;

    const backendUrl = process.env.REACT_APP_BACKEND_URL || "";
    // Convert http(s) to ws(s)
    const wsBase = backendUrl
      .replace(/^https:\/\//, "wss://")
      .replace(/^http:\/\//, "ws://");

    // No token in URL — auth happens via first message (H9)
    const url = `${wsBase}${path}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;
    authedRef.current = false;

    ws.onopen = () => {
      // Send auth as first message instead of query parameter
      ws.send(JSON.stringify({ type: "auth", token }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Handle auth handshake messages
        if (!authedRef.current) {
          if (data.type === "auth_ok") {
            authedRef.current = true;
            attemptRef.current = 0;
            setConnected(true);
            setReconnecting(false);
          } else if (data.type === "auth_error") {
            // Auth failed — server will close the connection
            console.warn("WebSocket auth failed:", data.detail);
          }
          return;
        }

        // Respond to server heartbeat pings
        if (data.type === "ping") {
          ws.send(JSON.stringify({ type: "pong" }));
          return;
        }

        onMessageRef.current(data);
      } catch {
        // ignore non-JSON frames
      }
    };

    ws.onclose = (event) => {
      setConnected(false);
      wsRef.current = null;
      authedRef.current = false;

      // Don't reconnect on intentional close or auth failure
      if (event.code === 1000 || event.code === 4001 || event.code === 4003) {
        setReconnecting(false);
        return;
      }

      if (attemptRef.current < MAX_RECONNECT_ATTEMPTS) {
        setReconnecting(true);
        const delay = Math.min(
          RECONNECT_BASE_MS * Math.pow(2, attemptRef.current),
          RECONNECT_CAP_MS
        );
        attemptRef.current += 1;
        timerRef.current = setTimeout(connect, delay);
      } else {
        setReconnecting(false);
      }
    };

    ws.onerror = () => {
      // onclose will fire after onerror — reconnect logic lives there
    };
  }, [enabled, token, path]);

  useEffect(() => {
    connect();

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // prevent reconnect on unmount
        wsRef.current.close(1000);
      }
      setConnected(false);
      setReconnecting(false);
    };
  }, [connect]);

  return { connected, reconnecting };
}
