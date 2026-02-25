import React, { useEffect, useRef } from "react";
import { X } from "lucide-react";

/**
 * Shared accessible modal component.
 *
 * Features:
 * - role="dialog" + aria-modal="true"
 * - Focus trapping (Tab cycles within modal)
 * - Escape key to close
 * - Click-outside-to-close on backdrop
 */
const Modal = ({ title, onClose, children }) => {
  const dialogRef = useRef(null);
  const previousFocus = useRef(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // Stable keydown handler — reads onClose from ref to avoid
  // re-running the effect (which would steal input focus).
  useEffect(() => {
    previousFocus.current = document.activeElement;
    dialogRef.current?.focus();

    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab") return;

      const focusable = dialogRef.current?.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (!focusable || focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previousFocus.current?.focus();
    };
  }, []); // mount-only: focus once, attach listener once

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6 outline-none"
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-slate-800">{title}</h3>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            className="p-1 rounded hover:bg-slate-100"
          >
            <X className="h-5 w-5 text-slate-400" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
};

export default Modal;
