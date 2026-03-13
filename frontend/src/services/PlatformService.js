/**
 * Platform Super Admin API service.
 * All endpoints require SUPER_ADMIN role.
 */
import axios from "axios";
import { getAccessToken, AuthService, clearAccessToken } from "@/services/api";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const platformAPI = axios.create({
  baseURL: `${BACKEND_URL}/api/v1/platform`,
  withCredentials: true,
});

platformAPI.interceptors.request.use((config) => {
  config.headers = config.headers || {};
  config.headers["Cache-Control"] = "no-cache";
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// On 401, refresh the access token then retry once (mirrors the main API interceptor).
let _refreshPromise = null;

platformAPI.interceptors.response.use(
  (res) => res,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        if (!_refreshPromise) {
          _refreshPromise = AuthService.refresh().finally(() => {
            _refreshPromise = null;
          });
        }
        const newToken = await _refreshPromise;
        originalRequest.headers = originalRequest.headers || {};
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return platformAPI(originalRequest);
      } catch {
        clearAccessToken();
        window.dispatchEvent(new Event("session-expired"));
      }
    }
    return Promise.reject(error);
  }
);

export const PlatformService = {
  /** Platform-wide stats */
  getStats: () => platformAPI.get("/stats/").then((r) => r.data),

  /** Paginated org list */
  getOrgs: (params = {}) => platformAPI.get("/orgs/", { params }).then((r) => r.data),

  /** Create a new lab org */
  createOrg: (data) => platformAPI.post("/orgs/create/", data).then((r) => r.data),

  /** Full org detail (users, billing, usage history) */
  getOrg: (schema) => platformAPI.get(`/orgs/${schema}/`).then((r) => r.data),

  /** Suspend or reactivate an org */
  updateOrg: (schema, data) => platformAPI.patch(`/orgs/${schema}/`, data).then((r) => r.data),

  /** Permanently delete an org */
  deleteOrg: (schema) => platformAPI.delete(`/orgs/${schema}/`).then((r) => r.data),

  /** 12-month usage history for one org */
  getOrgUsage: (schema) => platformAPI.get(`/orgs/${schema}/usage/`).then((r) => r.data),

  /** List users in an org */
  getOrgUsers: (schema) => platformAPI.get(`/orgs/${schema}/users/`).then((r) => r.data),

  /** Create a user in an org */
  createOrgUser: (schema, data) =>
    platformAPI.post(`/orgs/${schema}/users/`, data).then((r) => r.data),

  /** Override an org's plan directly (no Razorpay) */
  changeOrgPlan: (schema, planName) =>
    platformAPI.post(`/orgs/${schema}/plan/`, { plan: planName }).then((r) => r.data),

  /** Resend credentials email to a user */
  resendCredentials: (schema, userId) =>
    platformAPI.post(`/orgs/${schema}/users/${userId}/resend-credentials/`).then((r) => r.data),
};
