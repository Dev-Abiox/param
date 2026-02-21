/**
 * useSessionTimeout
 *
 * Tracks user activity and fires onTimeout() after TIMEOUT_MS of inactivity.
 * One minute before the deadline it sets showWarning=true so the UI can
 * prompt the user to stay signed in.
 *
 * Activity events that reset the clock:
 *   mousemove, keydown, click, scroll, touchstart
 */

import { useCallback, useEffect, useRef, useState } from "react";

const TIMEOUT_MS = 15 * 60 * 1000;   // 15 minutes
const WARNING_MS =  1 * 60 * 1000;   //  1 minute warning before expiry

/**
 * @param {object} options
 * @param {() => void} options.onTimeout - Called when the session expires.
 * @param {boolean}    [options.enabled=true] - Pass false when no user is logged in.
 * @returns {{ showWarning: boolean, resetTimer: () => void }}
 */
export function useSessionTimeout({ onTimeout, enabled = true }) {
  const [showWarning, setShowWarning] = useState(false);
  const timeoutRef = useRef(null);
  const warningRef = useRef(null);

  // Stable reset function — clears both timers and restarts them.
  const resetTimer = useCallback(() => {
    clearTimeout(timeoutRef.current);
    clearTimeout(warningRef.current);
    setShowWarning(false);

    if (!enabled) return;

    warningRef.current = setTimeout(() => {
      setShowWarning(true);
    }, TIMEOUT_MS - WARNING_MS);

    timeoutRef.current = setTimeout(() => {
      onTimeout();
    }, TIMEOUT_MS);
  }, [enabled, onTimeout]);

  useEffect(() => {
    if (!enabled) return;

    const events = ["mousemove", "keydown", "click", "scroll", "touchstart"];
    events.forEach((e) => window.addEventListener(e, resetTimer, { passive: true }));
    resetTimer();   // start the clock immediately on mount

    return () => {
      events.forEach((e) => window.removeEventListener(e, resetTimer));
      clearTimeout(timeoutRef.current);
      clearTimeout(warningRef.current);
    };
  }, [enabled, resetTimer]);

  return { showWarning, resetTimer };
}
