import React, { useState, useEffect, useRef } from "react";
import { Upload, FileText, Play, RotateCcw, Activity, Stethoscope, FileCheck, CheckCircle, X } from "lucide-react";

import { INITIAL_CBC_ROWS } from "../constants";
import CBCTable from "../components/CBCTable";
import ResultPanel from "../components/ResultPanel";
import ConsentCapture from "../components/ConsentCapture";
import { LisService, ConsentService } from "../services/api";
import { Role } from "../types";
import { parsePdf } from "../lib/parsePdf";

const UserWorkspace = ({ user }) => {
  // Fetch doctors for LAB role
  const [doctors, setDoctors] = useState([]);
  const [loadingDoctors, setLoadingDoctors] = useState(false);

  // Initialize patient with user's doctor_code if DOCTOR role
  const [patient, setPatient] = useState({
    id: "",
    name: "",
    age: 0,
    sex: "F",
    date: new Date().toISOString().split("T")[0],
    labId: user?.lab_code || "",
    referringDoctor: user?.role === Role.DOCTOR ? (user?.doctor_code || "") : "",
  });

  // Fetch doctors when component mounts (for LAB role)
  useEffect(() => {
    if (user?.role === Role.LAB && user?.lab_code) {
      const fetchDoctors = async () => {
        setLoadingDoctors(true);
        try {
          const data = await LisService.getDoctors(user?.lab_code);
          setDoctors(data);
        } catch (e) {
          console.error("Failed to load doctors", e);
        } finally {
          setLoadingDoctors(false);
        }
      };
      fetchDoctors();
    }
  }, [user?.role, user?.lab_code]);

  const [rows, setRows] = useState(INITIAL_CBC_ROWS);
  const [activeTab, setActiveTab] = useState("manual");
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState(null);
  const [uploadStatus, setUploadStatus] = useState("");
  const [screeningError, setScreeningError] = useState(null);

  // Consent state
  const [showConsentCapture, setShowConsentCapture] = useState(false);
  const [consentId, setConsentId] = useState(null);
  const [hasValidConsent, setHasValidConsent] = useState(false);

  const fileInputRef = useRef(null);

  const handleCBCChange = (key, value) => {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, value } : r)));
  };

  const handlePDFUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadStatus("Scanning PDF...");
    setIsProcessing(true);
    setScreeningError(null);
    try {
      const { cbc, patient: pdfPatient } = await parsePdf(file, setUploadStatus);

      // Populate CBC values
      setRows((prev) =>
        prev.map((r) => ({
          ...r,
          value: cbc[r.key] !== undefined ? String(cbc[r.key]) : r.value,
        }))
      );

      // Populate patient info from PDF
      setPatient((prev) => ({
        ...prev,
        name: pdfPatient.name || prev.name,
        age: pdfPatient.age || prev.age,
        sex: pdfPatient.sex || prev.sex,
        id: pdfPatient.id || prev.id,
      }));

      const extractedCount = Object.keys(cbc).length;
      setUploadStatus(
        `Extracted ${extractedCount}/11 CBC values${pdfPatient.name ? " + patient info" : ""}. Please verify below.`
      );
      setActiveTab("manual");
      setHasValidConsent(false);
      setConsentId(null);
      setResult(null);
    } catch (err) {
      console.error("PDF parse error:", err);
      setUploadStatus("Error reading PDF. Please ensure it's a valid lab report.");
    } finally {
      setIsProcessing(false);
      // Reset file input so the same file can be re-uploaded
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const checkExistingConsent = async () => {
    if (!patient.id) return null;
    try {
      const status = await ConsentService.getStatus(patient.id);
      if (status.hasConsent) {
        setConsentId(status.consentId);
        setHasValidConsent(true);
        return status.consentId;
      }
    } catch (err) {
      console.error("Failed to check consent:", err);
    }
    return null;
  };

  const handleConsentCaptured = async (consentData) => {
    const result = await ConsentService.record(patient.id, consentData);
    setConsentId(result.id);
    setHasValidConsent(true);
    setShowConsentCapture(false);
    // Automatically run screening after consent
    await runScreeningWithConsent(result.id);
  };

  const runScreeningWithConsent = async (consentIdToUse) => {
    setIsProcessing(true);
    setScreeningError(null);
    try {
      const cbcData = {};
      rows.forEach((r) => {
        const val = parseFloat(r.value);
        if (!Number.isNaN(val)) cbcData[r.key] = val;
      });

      const res = await LisService.predictB12(cbcData, patient, consentIdToUse);
      setResult(res);
    } catch (err) {
      console.error("Screening Error:", err);
      setResult(null);
      setScreeningError("Screening failed. Please verify inputs and try again.");
    } finally {
      setIsProcessing(false);
    }
  };

  const runScreening = async () => {
    setScreeningError(null);

    if (!patient.id) {
      setScreeningError("Patient ID is required to run screening.");
      return;
    }

    // Check for existing consent — returns the consentId directly
    // (cannot rely on React state which updates asynchronously)
    const existingConsentId = await checkExistingConsent();

    if (existingConsentId) {
      // Run with existing consent
      runScreeningWithConsent(existingConsentId);
    } else {
      // Show consent capture
      setShowConsentCapture(true);
    }
  };

  const resetForm = () => {
    setResult(null);
    setScreeningError(null);
    setRows(INITIAL_CBC_ROWS.map((r) => ({ ...r, value: "" })));
    setPatient((prev) => ({ ...prev, id: "", name: "" }));
    setConsentId(null);
    setHasValidConsent(false);
    setShowConsentCapture(false);
  };

  return (
    <>
      {/* Consent Modal Popup */}
      {showConsentCapture && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="consent-modal">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => setShowConsentCapture(false)}
          />
          {/* Modal Content */}
          <div className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-white dark:bg-slate-900 rounded-xl shadow-2xl animate-in fade-in zoom-in duration-200">
            {/* Close Button */}
            <button
              onClick={() => setShowConsentCapture(false)}
              aria-label="Close consent capture"
              className="absolute top-4 right-4 p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 z-10"
            >
              <X className="h-5 w-5 text-slate-500 dark:text-slate-400" />
            </button>
            <ConsentCapture
              patient={patient}
              onConsentCaptured={handleConsentCaptured}
              onCancel={() => setShowConsentCapture(false)}
            />
          </div>
        </div>
      )}

      {/* Main Content */}
      <div data-testid="workspace-page" className="w-full space-y-6">
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        <div className="xl:col-span-6 space-y-6">
          <section className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 rounded-sm shadow-sm overflow-hidden">
            <div className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 px-4 py-3 flex items-center justify-between">
              <h3 className="font-bold text-slate-700 dark:text-slate-300 text-sm uppercase tracking-wide">Patient Registration</h3>
              <span className="text-xs font-mono text-slate-500 dark:text-slate-400">{patient.labId || "No lab configured"}</span>
            </div>
            {!user?.lab_code && user?.role === Role.LAB && (
              <div className="px-4 py-3 bg-amber-50 dark:bg-amber-900/30 border-b border-amber-100 dark:border-amber-800 text-sm text-amber-700 dark:text-amber-400">
                <p>No lab has been configured for this account. Please contact an administrator to assign a lab.</p>
              </div>
            )}
            <div className="p-4 grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">Full Name</label>
                <input
                  data-testid="patient-name-input"
                  type="text"
                  className="w-full border border-slate-300 dark:border-slate-600 rounded px-2 py-1.5 text-sm focus:ring-1 focus:ring-teal-500 focus:border-teal-500 bg-white dark:bg-slate-800 text-black dark:text-white"
                  placeholder="Doe, Jane"
                  value={patient.name}
                  onChange={(e) => setPatient({ ...patient, name: e.target.value })}
                />
              </div>
              {/* Referring Doctor - Only show for LAB role, auto-set for DOCTOR role */}
              {user?.role === Role.LAB ? (
                <div className="col-span-2">
                  <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">Referring Doctor</label>
                  <div className="relative">
                    <Stethoscope className="w-4 h-4 absolute left-2 top-2 text-slate-400 dark:text-slate-500" />
                    <select
                      data-testid="referring-doctor-select"
                      className="w-full border border-slate-300 dark:border-slate-600 rounded pl-8 pr-2 py-1.5 text-sm bg-white dark:bg-slate-800 text-black dark:text-white"
                      value={patient.referringDoctor}
                      onChange={(e) => setPatient({ ...patient, referringDoctor: e.target.value })}
                      disabled={loadingDoctors}
                    >
                      <option value="">{loadingDoctors ? "Loading doctors..." : "Select Physician..."}</option>
                      {doctors.map((doc) => (
                        <option key={doc.code} value={doc.code}>
                          Dr. {doc.name} ({doc.dept || "General"})
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              ) : user?.role === Role.DOCTOR ? (
                <div className="col-span-2">
                  <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">Referring Doctor</label>
                  <div className="flex items-center p-2 bg-blue-50 dark:bg-blue-900/30 border border-blue-100 dark:border-blue-800 rounded text-sm text-blue-700 dark:text-blue-400">
                    <Stethoscope className="h-4 w-4 mr-2" />
                    <span>Dr. {user?.name} (You)</span>
                  </div>
                </div>
              ) : null}
              <div>
                <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">Age</label>
                <input
                  data-testid="patient-age-input"
                  type="number"
                  className="w-full border border-slate-300 dark:border-slate-600 rounded px-2 py-1.5 text-sm bg-white dark:bg-slate-800 text-black dark:text-white"
                  value={patient.age || ""}
                  onChange={(e) => setPatient({ ...patient, age: parseInt(e.target.value || "0", 10) })}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">Sex</label>
                <select
                  data-testid="patient-sex-select"
                  className="w-full border border-slate-300 dark:border-slate-600 rounded px-2 py-1.5 text-sm bg-white dark:bg-slate-800 dark:text-white"
                  value={patient.sex}
                  onChange={(e) => setPatient({ ...patient, sex: e.target.value })}
                >
                  <option value="F">Female</option>
                  <option value="M">Male</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">Patient ID</label>
                <input
                  data-testid="patient-id-input"
                  type="text"
                  className="w-full border border-slate-300 dark:border-slate-600 rounded px-2 py-1.5 text-sm font-mono bg-white dark:bg-slate-800 text-black dark:text-white"
                  value={patient.id}
                  onChange={(e) => {
                    setPatient({ ...patient, id: e.target.value });
                    setHasValidConsent(false);
                    setConsentId(null);
                  }}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">Date</label>
                <input
                  data-testid="patient-date-input"
                  type="date"
                  className="w-full border border-slate-300 dark:border-slate-600 rounded px-2 py-1.5 text-sm bg-white dark:bg-slate-800 text-black dark:text-white"
                  value={patient.date}
                  onChange={(e) => setPatient({ ...patient, date: e.target.value })}
                />
              </div>

              {/* Consent Status Indicator */}
              {patient.id && (
                <div className="col-span-2">
                  {hasValidConsent ? (
                    <div className="flex items-center p-2 bg-green-50 dark:bg-green-900/30 border border-green-100 dark:border-green-800 rounded text-sm text-green-700 dark:text-green-400">
                      <CheckCircle className="h-4 w-4 mr-2" />
                      <span>Consent recorded (ID: {consentId?.slice(0, 8)}...)</span>
                    </div>
                  ) : (
                    <div className="flex items-center p-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded text-sm text-slate-600 dark:text-slate-300">
                      <FileCheck className="h-4 w-4 mr-2" />
                      <span>Consent will be captured before screening</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>

          <div className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 rounded-sm shadow-sm overflow-hidden">
            <div className="border-b border-slate-200 dark:border-slate-700 flex">
              <button
                data-testid="tab-manual"
                onClick={() => setActiveTab("manual")}
                className={`flex-1 py-3 text-sm font-medium flex items-center justify-center ${
                  activeTab === "manual" ? "text-teal-700 border-b-2 border-teal-600 bg-teal-50/50" : "text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800"
                }`}
              >
                <FileText className="w-4 h-4 mr-2" />
                Manual Entry
              </button>
              <button
                data-testid="tab-pdf"
                onClick={() => setActiveTab("pdf")}
                className={`flex-1 py-3 text-sm font-medium flex items-center justify-center ${
                  activeTab === "pdf" ? "text-teal-700 border-b-2 border-teal-600 bg-teal-50/50" : "text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800"
                }`}
              >
                <Upload className="w-4 h-4 mr-2" />
                Import PDF Report
              </button>
            </div>

            {activeTab === "pdf" && (
              <div className="p-6 bg-slate-50 dark:bg-slate-800">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf"
                  onChange={handlePDFUpload}
                  className="hidden"
                  data-testid="pdf-file-input"
                />
                <div
                  className="border-2 border-dashed border-slate-300 dark:border-slate-600 rounded-lg p-8 text-center bg-white dark:bg-slate-900 hover:border-teal-400 hover:bg-teal-50/30 transition-colors cursor-pointer"
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
                  onDrop={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const file = e.dataTransfer.files?.[0];
                    if (file && file.type === "application/pdf") {
                      handlePDFUpload({ target: { files: [file] } });
                    }
                  }}
                >
                  {isProcessing ? (
                    <>
                      <div className="w-10 h-10 border-4 border-teal-200 border-t-teal-600 rounded-full animate-spin mx-auto mb-3" />
                      <p className="text-sm text-teal-700 font-medium">{uploadStatus}</p>
                    </>
                  ) : (
                    <>
                      <Upload className="w-10 h-10 text-teal-500 mx-auto mb-3" />
                      <p className="text-sm text-slate-700 dark:text-slate-300 font-medium">
                        Click to upload or drag & drop a CBC report PDF
                      </p>
                      <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                        Supports standard lab report formats. Values will be extracted and shown for verification.
                      </p>
                    </>
                  )}
                </div>
                {uploadStatus && !isProcessing && (
                  <p className="mt-3 text-sm text-teal-700 font-medium text-center">{uploadStatus}</p>
                )}
              </div>
            )}

            <div className={`${activeTab === "manual" ? "block" : "hidden"}`}>
              <CBCTable rows={rows} patientSex={patient.sex} onValueChange={handleCBCChange} />
            </div>

            {screeningError && (
              <div data-testid="screening-error" className="px-4 py-3 bg-red-50 dark:bg-red-900/30 border-t border-red-100 dark:border-red-800 text-sm text-red-700 dark:text-red-400">
                {screeningError}
              </div>
            )}

            <div className="p-4 bg-slate-50 dark:bg-slate-800 border-t border-slate-200 dark:border-slate-700 flex justify-between items-center gap-2">
              <button data-testid="reset-form-button" onClick={resetForm} className="px-4 py-2 border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800 flex items-center">
                <RotateCcw className="w-4 h-4 mr-2" /> Reset
              </button>

              <button
                data-testid="run-screening-button"
                onClick={runScreening}
                disabled={isProcessing}
                className="px-6 py-2 bg-teal-700 rounded text-white text-sm font-bold hover:bg-teal-800 shadow-sm flex items-center disabled:opacity-50"
              >
                {isProcessing ? (
                  "Analyzing..."
                ) : (
                  <>
                    <Play className="w-4 h-4 mr-2 fill-current" /> Run B12 Screening
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        <div className="xl:col-span-6">
          {result ? (
            <ResultPanel result={result} patient={patient} cbcRows={rows} />
          ) : (
            <div className="h-full min-h-[500px] border-2 border-dashed border-slate-300 dark:border-slate-600 rounded-sm bg-slate-50 dark:bg-slate-800 flex flex-col items-center justify-center text-slate-400 dark:text-slate-500" data-testid="no-results-empty">
              <div className="bg-white dark:bg-slate-900 p-6 rounded-full shadow-sm mb-4">
                <Activity className="w-12 h-12 text-slate-300 dark:text-slate-600" />
              </div>
              <h3 className="text-lg font-medium text-slate-500 dark:text-slate-400">No Analysis Results Yet</h3>
              <p className="max-w-xs text-center text-sm mt-2">Enter CBC values manually or upload a report, then click "Run Screening" to see B12 deficiency risk analysis.</p>
            </div>
          )}
        </div>
      </div>
      </div>
    </>
  );
};

export default UserWorkspace;
