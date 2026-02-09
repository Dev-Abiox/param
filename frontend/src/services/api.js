import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

// Generate a unique request ID
const generateRequestId = () => {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
};

const API = axios.create({
  baseURL: `${BACKEND_URL}/api`,
});

// Add request ID and auth token to all requests
API.interceptors.request.use((config) => {
  // Add request ID parameter
  config.params = config.params || {};
  config.params.r = generateRequestId();
  
  // Add auth token
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

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
        await AuthService.logout();
      }
    }
    return Promise.reject(error);
  }
);

export const AuthService = {
  login: async (username, password, mfaCode = null) => {
    const payload = { username, password };
    if (mfaCode) {
      payload.mfa_code = mfaCode;
    }
    const res = await API.post("/auth/login", payload);
    
    // Check if MFA is required
    if (res.data.mfa_required && res.data.mfa_pending_token) {
      return {
        mfaRequired: true,
        mfaPendingToken: res.data.mfa_pending_token,
        id: res.data.id,
        name: res.data.name,
        role: res.data.role,
      };
    }
    
    // Normal login - store tokens
    localStorage.setItem("access_token", res.data.access_token);
    localStorage.setItem("refresh_token", res.data.refresh_token);
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
    
    localStorage.setItem("access_token", res.data.access_token);
    localStorage.setItem("refresh_token", res.data.refresh_token);
    return {
      id: res.data.id,
      name: res.data.name,
      role: res.data.role,
    };
  },
  
  refresh: async () => {
    const refreshToken = localStorage.getItem("refresh_token");
    if (!refreshToken) throw new Error("No refresh token");
    const res = await API.post("/auth/refresh", { refresh_token: refreshToken });
    localStorage.setItem("access_token", res.data.access_token);
    localStorage.setItem("refresh_token", res.data.refresh_token);
    return res.data.access_token;
  },
  
  logout: async () => {
    const refreshToken = localStorage.getItem("refresh_token");
    try {
      if (refreshToken) {
        await API.post("/auth/logout", { refresh_token: refreshToken });
      }
    } finally {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
    }
  },
  
  getMe: async () => {
    const res = await API.get("/auth/me");
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
  uploadPdf: async (file) => {
    const formData = new FormData();
    formData.append("file", file);
    const res = await API.post("/lis/parse-pdf", formData);
    return res.data.cbc;
  },

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

  getPatientRecords: async (doctorId, labId) => {
    const res = await API.get("/analytics/cases", { params: { doctorId, labId } });
    return res.data;
  },

  getStats: async () => {
    const res = await API.get("/analytics/summary");
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
    const res = await API.get("/admin/system/health");
    return res.data;
  },
  
  getSystemConfig: async () => {
    const res = await API.get("/admin/system/config");
    return res.data;
  },
};
