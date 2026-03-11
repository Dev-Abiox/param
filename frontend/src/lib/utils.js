import { clsx } from "clsx";
import { twMerge } from "tailwind-merge"

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

/**
 * Extract the best error message from an axios error.
 * Checks both custom `error` field and DRF's standard `detail` field.
 */
export function extractApiError(err, fallback = "Something went wrong.") {
  const data = err?.response?.data;
  return (
    data?.error
    || data?.detail
    || (err?.response?.status ? `Server error (${err.response.status})` : null)
    || fallback
  );
}
