import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

// In-memory access token — never touches localStorage or sessionStorage.
// The refresh token lives in an httpOnly cookie (set by the backend).
let _accessToken = null;

export const setAccessToken = (token) => { _accessToken = token; };
export const clearAccessToken = () => { _accessToken = null; };

// Generate a unique request ID
const generateRequestId = () => {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
};

const API = axios.create({
  baseURL: `${BACKEND_URL}/api`,
  withCredentials: true,   // send the httpOnly refresh-token cookie on every request
});

// Plain instance with NO interceptors — used only for token refresh so that
// a 401 from the refresh endpoint propagates directly without triggering
// another refresh attempt and looping.
const _refreshAPI = axios.create({
  baseURL: `${BACKEND_URL}/api`,
  withCredentials: true,
});

// Attach access token and a cache-busting request ID to every outbound request
API.interceptors.request.use((config) => {
  config.params = config.params || {};
  config.params.r = generateRequestId();

  if (_accessToken) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${_accessToken}`;
  }
  return config;
});

// On 401, silently refresh the access token (using the cookie) then retry once
API.interceptors.response.use(
  (res) => res,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        const newToken = await AuthService.refresh();
        originalRequest.headers = originalRequest.headers || {};
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return API(originalRequest);
      } catch (e) {
        clearAccessToken();
        // Notify the app that the session has fully expired
        window.dispatchEvent(new Event("session-expired"));
      }
    }
    return Promise.reject(error);
  }
);

export const AuthService = {
  login: async (username, password, mfaCode = null) => {
    const payload = { username, password };
    if (mfaCode) payload.mfa_code = mfaCode;

    const res = await API.post("/auth/login", payload);

    // MFA required — no tokens issued yet
    if (res.data.mfa_required && res.data.mfa_pending_token) {
      return {
        mfaRequired: true,
        mfaPendingToken: res.data.mfa_pending_token,
        id: res.data.id,
        name: res.data.name,
        role: res.data.role,
      };
    }

    // Full login — access token in body, refresh token in httpOnly cookie
    setAccessToken(res.data.access_token);
    return {
      mfaRequired: false,
      id: res.data.id,
      name: res.data.name,
      role: res.data.role,
    };
  },

  verifyMFA: async (mfaPendingToken, mfaCode) => {
    const res = await API.post("/auth/mfa/verify", {
      mfa_pending_token: mfaPendingToken,
      mfa_code: mfaCode,
    });

    setAccessToken(res.data.access_token);
    return {
      id: res.data.id,
      name: res.data.name,
      role: res.data.role,
    };
  },

  // Silently exchange the httpOnly refresh cookie for a new access token.
  // Called on app startup and by the 401 interceptor.
  refresh: async () => {
    const res = await _refreshAPI.post("/auth/refresh");   // plain instance — no interceptor loop
    setAccessToken(res.data.access_token);
    return res.data.access_token;
  },

  logout: async () => {
    try {
      await API.post("/auth/logout");   // cookie is sent + deleted by the server
    } finally {
      clearAccessToken();
    }
  },

  getMe: async () => {
    const res = await API.get("/auth/me");
    return res.data;
  },

  forgotPassword: async (identifier) => {
    const res = await API.post("/auth/forgot-password", { identifier });
    return res.data;
  },

  resetPassword: async (token, newPassword) => {
    const res = await API.post("/auth/reset-password", { token, new_password: newPassword });
    return res.data;
  },

  getSessions: async () => {
    const res = await API.get("/auth/sessions");
    return res.data;
  },

  revokeSession: async (tokenId) => {
    const res = await API.delete(`/auth/sessions/${tokenId}`);
    return res.data;
  },

  signup: async ({ orgName, adminEmail, adminPassword, plan, adminName }) => {
    const res = await API.post("/v1/signup/", {
      org_name: orgName,
      admin_email: adminEmail,
      admin_password: adminPassword,
      plan,
      admin_name: adminName,
    });
    if (res.data.access_token) {
      setAccessToken(res.data.access_token);
    }
    return res.data;
  },
};

export const MFAService = {
  getStatus: async () => {
    const res = await API.get("/mfa/status");
    return res.data;
  },
  
  setup: async (email) => {
    const res = await API.post("/mfa/setup", { email });
    return res.data;
  },
  
  verifySetup: async (code) => {
    const res = await API.post("/mfa/verify-setup", { code });
    return res.data;
  },
  
  disable: async (code) => {
    const res = await API.post("/mfa/disable", { code });
    return res.data;
  },
  
  regenerateBackupCodes: async (code) => {
    const res = await API.post("/mfa/backup-codes/regenerate", { code });
    return res.data;
  },
};

export const ConsentService = {
  getStatus: async (patientId) => {
    try {
      const res = await API.get(`/screening/consent/status/${patientId}`);
      return res.data;
    } catch (e) {
      return { hasConsent: false };
    }
  },

  record: async (patientId, consentData) => {
    const res = await API.post("/screening/consent/record", consentData);
    return res.data;
  },
};

export const LisService = {
  predictB12: async (cbcData, patient, consentId = null) => {
    const payload = {
      patientId: patient.id,
      patientName: patient.name || "",
      labId: patient.labId || "",
      doctorId: patient.referringDoctor || "",
      consentId: consentId,
      cbc: {
        Hb_g_dL: cbcData.hb,
        RBC_million_uL: cbcData.rbc,
        HCT_percent: cbcData.hct,
        MCV_fL: cbcData.mcv,
        MCH_pg: cbcData.mch,
        MCHC_g_dL: cbcData.mchc,
        RDW_percent: cbcData.rdw,
        WBC_10_3_uL: cbcData.wbc,
        Platelets_10_3_uL: cbcData.plt,
        Neutrophils_percent: cbcData.neu_pct,
        Lymphocytes_percent: cbcData.lym_pct,
        Age: patient.age,
        Sex: patient.sex,
      },
    };

    const res = await API.post("/screening/predict", payload);

    return {
      label: res.data.label,
      probabilities: res.data.probabilities,
      indices: res.data.indices,
      recommendation: res.data.recommendation,
      interpretation: (res.data.rulesFired || []).join(", "),
    };
  },

  getLabs: async () => {
    const res = await API.get("/analytics/labs");
    return res.data;
  },

  getDoctors: async (labId) => {
    const res = await API.get("/analytics/doctors", { params: { labId } });
    return res.data;
  },

  getPatientRecords: async (doctorId, labId, page = 1, pageSize = 50) => {
    const res = await API.get("/analytics/cases", { params: { doctorId, labId, page, page_size: pageSize } });
    return res.data;
  },

  getStats: async () => {
    const res = await API.get("/analytics/summary");
    return res.data;
  },

  getScreening: async (screeningId) => {
    const res = await API.get(`/analytics/screening/${screeningId}`);
    return res.data;
  },

  // 3.4 — Patient CBC trend
  getPatientTrend: async (patientId) => {
    const res = await API.get(`/analytics/trend/${patientId}`);
    return res.data;
  },

  // 3.2 — Work queue
  getWorkQueue: async (status = 'pending') => {
    const res = await API.get('/screening/queue', { params: { status } });
    return res.data;
  },

  updateScreeningStatus: async (screeningId, newStatus) => {
    const res = await API.patch(`/screening/cases/${screeningId}/status`, { status: newStatus });
    return res.data;
  },

  // 3.3 — Doctor review
  reviewScreening: async (screeningId, clinicalNote = '') => {
    const res = await API.patch(`/screening/cases/${screeningId}/review`, { clinical_note: clinicalNote });
    return res.data;
  },

  // 5.3 — Bulk Import
  submitBulkImport: async (file, labId = '') => {
    const form = new FormData();
    form.append('file', file);
    const res = await API.post('/screening/bulk-import', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: labId ? { labId } : {},
    });
    return res.data;
  },

  getBulkImportStatus: async (jobId) => {
    const res = await API.get(`/screening/bulk-import/${jobId}/status`);
    return res.data;
  },
};

export const AdminService = {
  getAuditSummary: async () => {
    const res = await API.get("/admin/audit/v2/summary");
    return res.data;
  },

  verifyAuditChain: async (limit = 100) => {
    const res = await API.get(`/admin/audit/v2/verify?limit=${limit}`);
    return res.data;
  },

  exportAuditLogs: async (fromSequence = 1, toSequence = null) => {
    const params = { from_sequence: fromSequence };
    if (toSequence) params.to_sequence = toSequence;
    const res = await API.get("/admin/audit/v2/export", { params });
    return res.data;
  },

  getSystemHealth: async () => {
    const res = await API.get("/v1/health/ready");
    return res.data;
  },

  getSystemConfig: async () => {
    const res = await API.get("/v1/health/ready");
    return res.data;
  },

  // ── User Management ──────────────────────────────────────────────────────────
  getUsers: async () => {
    const res = await API.get("/admin/users");
    return res.data;
  },
  createUser: async (data) => {
    const res = await API.post("/admin/users", data);
    return res.data;
  },
  updateUser: async (userId, data) => {
    const res = await API.patch(`/admin/users/${userId}`, data);
    return res.data;
  },
  deactivateUser: async (userId) => {
    const res = await API.delete(`/admin/users/${userId}`);
    return res.data;
  },

  // ── Lab Management ───────────────────────────────────────────────────────────
  getLabs: async () => {
    const res = await API.get("/screening/admin/labs");
    return res.data;
  },
  createLab: async (data) => {
    const res = await API.post("/screening/admin/labs", data);
    return res.data;
  },
  updateLab: async (labId, data) => {
    const res = await API.patch(`/screening/admin/labs/${labId}`, data);
    return res.data;
  },
  deactivateLab: async (labId) => {
    const res = await API.delete(`/screening/admin/labs/${labId}`);
    return res.data;
  },

  // ── Doctor Management ────────────────────────────────────────────────────────
  getDoctors: async (labId = null) => {
    const params = labId ? { labId } : {};
    const res = await API.get("/screening/admin/doctors", { params });
    return res.data;
  },
  createDoctor: async (data) => {
    const res = await API.post("/screening/admin/doctors", data);
    return res.data;
  },
  updateDoctor: async (doctorId, data) => {
    const res = await API.patch(`/screening/admin/doctors/${doctorId}`, data);
    return res.data;
  },
  deactivateDoctor: async (doctorId) => {
    const res = await API.delete(`/screening/admin/doctors/${doctorId}`);
    return res.data;
  },
};

export const BillingService = {
  getUsage: async () => {
    const res = await API.get("/v1/billing/admin/usage");
    return res.data;
  },
  getPlan: async () => {
    const res = await API.get("/v1/billing/admin/billing");
    return res.data;
  },
  upgradePlan: async (planName) => {
    const res = await API.post("/v1/billing/admin/billing/upgrade", { plan: planName });
    return res.data;
  },
  getOnboardingStatus: async () => {
    const res = await API.get("/v1/billing/onboarding/");
    return res.data;
  },
  updateOnboardingStatus: async (updates) => {
    const res = await API.patch("/v1/billing/onboarding/", updates);
    return res.data;
  },
};

export const NotificationService = {
  getAll: async () => {
    const res = await API.get("/notifications/");
    return res.data;
  },

  markRead: async (notificationId) => {
    const res = await API.post(`/notifications/${notificationId}/read`);
    return res.data;
  },
};
