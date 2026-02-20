import React, { useEffect, useRef, useCallback } from "react";
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

  // Trap focus within the modal
  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === "Escape") {
        onClose();
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
    },
    [onClose]
  );

  useEffect(() => {
    previousFocus.current = document.activeElement;
    // Focus the dialog itself on mount
    dialogRef.current?.focus();
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      // Restore focus on unmount
      previousFocus.current?.focus();
    };
  }, [handleKeyDown]);

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
