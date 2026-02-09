import axios from "axios";
import { ScreeningResult, ScreeningLabel, User, Role, PatientData } from "../types";

const API = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000",
});

// Attach JWT token automatically
API.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// -------------------- AUTH --------------------

export const AuthService = {
  login: async (username: string, password: string): Promise<User> => {
    const res = await API.post("/api/auth/login", { username, password });

    localStorage.setItem("access_token", res.data.access_token);

    return {
      id: res.data.id,
      name: res.data.name,
      role: res.data.role as Role,
    };
  }
};

// -------------------- LIS / B12 ENGINE --------------------

export const LisService = {

  uploadPdf: async (file: File): Promise<Record<string, number>> => {
    const formData = new FormData();
    formData.append("file", file);

    const res = await API.post("/api/lis/parse-pdf", formData);
    return res.data.cbc;
  },

  predictB12: async (cbcData: Record<string, number>, patient: PatientData): Promise<ScreeningResult> => {
    const payload = {
      patientId: patient.id,
      cbc: {
        Hb_g_dL: cbcData["hb"],
        RBC_million_uL: cbcData["rbc"],
        HCT_percent: cbcData["hct"],
        MCV_fL: cbcData["mcv"],
        MCH_pg: cbcData["mch"],
        MCHC_g_dL: cbcData["mchc"],
        RDW_percent: cbcData["rdw"],
        WBC_10_3_uL: cbcData["wbc"],
        Platelets_10_3_uL: cbcData["plt"],
        Neutrophils_percent: cbcData["neu_pct"],
        Lymphocytes_percent: cbcData["lym_pct"],
        Age: patient.age,
        Sex: patient.sex
      }
    };


    const res = await API.post("/api/screening/predict", payload);

    return {
      label: res.data.label as ScreeningLabel,
      probabilities: res.data.probabilities,
      indices: res.data.indices,
      recommendation: res.data.recommendation,
      interpretation: res.data.rulesFired.join(", ")
    };
  },

  saveCase: async (patient: PatientData, result: ScreeningResult): Promise<boolean> => {
    await API.post("/api/cases/save", { patient, result });
    return true;
  },

  getLabs: async () => {
    const res = await API.get("/api/analytics/labs");
    return res.data;
  },

  getDoctors: async (labId?: string) => {
    const res = await API.get("/api/analytics/doctors", { params: { labId } });
    return res.data;
  },

  getPatientRecords: async (doctorId?: string, labId?: string) => {
    const res = await API.get("/api/analytics/cases", { params: { doctorId, labId } });
    return res.data;
  },

  getStats: async () => {
    const res = await API.get("/api/analytics/summary");
    return res.data;
  }
};
