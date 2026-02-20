import { useEffect, useRef, useCallback, useState } from "react";

const RECONNECT_BASE_MS = 1000;
const RECONNECT_CAP_MS = 30000;
const MAX_RECONNECT_ATTEMPTS = 10;

/**
 * Custom hook for WebSocket connections with auto-reconnect.
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
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    if (!enabled || !token) return;

    const backendUrl = process.env.REACT_APP_BACKEND_URL || "";
    // Convert http(s) to ws(s)
    const wsBase = backendUrl
      .replace(/^https:\/\//, "wss://")
      .replace(/^http:\/\//, "ws://");

    const url = `${wsBase}${path}?token=${encodeURIComponent(token)}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      attemptRef.current = 0;
      setConnected(true);
      setReconnecting(false);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessageRef.current(data);
      } catch {
        // ignore non-JSON frames
      }
    };

    ws.onclose = (event) => {
      setConnected(false);
      wsRef.current = null;

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
