import React from "react";
import Modal from "./Modal";

/**
 * Confirmation dialog for destructive actions.
 *
 * @param {string}   title       - Dialog title
 * @param {string}   message     - Confirmation message
 * @param {string}   confirmText - Text for the confirm button (default "Confirm")
 * @param {boolean}  destructive - If true, confirm button is red (default false)
 * @param {Function} onConfirm   - Called when user confirms
 * @param {Function} onCancel    - Called when user cancels
 */
const ConfirmDialog = ({
  title,
  message,
  confirmText = "Confirm",
  destructive = false,
  onConfirm,
  onCancel,
}) => (
  <Modal title={title} onClose={onCancel}>
    <p className="text-sm text-slate-600 mb-6">{message}</p>
    <div className="flex justify-end gap-3">
      <button
        onClick={onCancel}
        className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 rounded-lg hover:bg-slate-200"
      >
        Cancel
      </button>
      <button
        onClick={onConfirm}
        className={`px-4 py-2 text-sm font-medium text-white rounded-lg ${
          destructive
            ? "bg-red-600 hover:bg-red-700"
            : "bg-teal-700 hover:bg-teal-800"
        }`}
      >
        {confirmText}
      </button>
    </div>
  </Modal>
);

export default ConfirmDialog;
