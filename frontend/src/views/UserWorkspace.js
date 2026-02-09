import React, { useState, useEffect } from "react";
import { Upload, FileText, Play, RotateCcw, Activity, Stethoscope, FileCheck, CheckCircle, Shuffle, Info, X } from "lucide-react";

import { INITIAL_CBC_ROWS } from "../constants";

// Realistic CBC data profiles based on clinical research
// Sources: Cleveland Clinic, NCBI, MedlinePlus - B12 deficiency indicators
const CBC_PROFILES = {
  normal: {
    label: "Normal",
    description: "Healthy CBC - all values within reference range",
    expectedB12: "Normal B12 levels expected",
    color: "green",
    getData: (sex) => ({
      hb: sex === "M" ? randRange(14.0, 16.5) : randRange(12.5, 14.5),
      rbc: sex === "M" ? randRange(4.7, 5.5) : randRange(4.2, 4.9),
      wbc: randRange(5.5, 9.0),
      plt: randRange(180, 350),
      hct: sex === "M" ? randRange(42, 50) : randRange(37, 44),
      mcv: randRange(82, 96),      // Normal MCV
      mch: randRange(28, 31),      // Normal MCH
      mchc: randRange(33, 35),
      rdw: randRange(11.8, 13.5),  // Normal RDW
      neu_pct: randRange(50, 65),
      lym_pct: randRange(25, 38),
    }),
  },
  borderline: {
    label: "Borderline",
    description: "Mild macrocytosis - early B12 deficiency pattern",
    expectedB12: "Borderline B12 - recommend serum B12 testing",
    color: "amber",
    getData: (sex) => ({
      hb: sex === "M" ? randRange(12.5, 14.0) : randRange(11.0, 12.5),
      rbc: sex === "M" ? randRange(4.0, 4.6) : randRange(3.7, 4.2),
      wbc: randRange(4.8, 8.5),
      plt: randRange(160, 300),
      hct: sex === "M" ? randRange(38, 43) : randRange(34, 39),
      mcv: randRange(97, 104),     // Elevated MCV (macrocytic)
      mch: randRange(31, 34),      // Elevated MCH
      mchc: randRange(32, 35),
      rdw: randRange(14.0, 16.0),  // Elevated RDW
      neu_pct: randRange(45, 62),
      lym_pct: randRange(28, 42),
    }),
  },
  deficient: {
    label: "Deficient",
    description: "Macrocytic anemia - classic B12 deficiency pattern",
    expectedB12: "High likelihood of B12 deficiency - urgent follow-up",
    color: "red",
    getData: (sex) => ({
      hb: sex === "M" ? randRange(9.5, 12.0) : randRange(8.5, 11.0),
      rbc: sex === "M" ? randRange(3.2, 4.0) : randRange(2.9, 3.7),
      wbc: randRange(3.8, 6.5),
      plt: randRange(120, 200),
      hct: sex === "M" ? randRange(30, 38) : randRange(28, 35),
      mcv: randRange(105, 125),    // High MCV (macrocytic anemia)
      mch: randRange(34, 40),      // High MCH
      mchc: randRange(32, 36),
      rdw: randRange(16.0, 22.0),  // High RDW (anisocytosis)
      neu_pct: randRange(35, 55),
      lym_pct: randRange(30, 48),
    }),
  },
};

// Helper function for random range with 1 decimal precision
function randRange(min, max) {
  return (Math.random() * (max - min) + min).toFixed(1);
}
import CBCTable from "../components/CBCTable";
import ResultPanel from "../components/ResultPanel";
import ConsentCapture from "../components/ConsentCapture";
import { LisService, ConsentService } from "../services/api";
import { Role } from "../types";

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
    labId: user?.lab_code || "LAB-2024-001",
    referringDoctor: user?.role === Role.DOCTOR ? (user?.doctor_code || "") : "",
  });

  // Fetch doctors when component mounts (for LAB role)
  useEffect(() => {
    if (user?.role === Role.LAB) {
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

  // Random data state
  const [randomProfile, setRandomProfile] = useState(null);

  const handleCBCChange = (key, value) => {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, value } : r)));
  };

  const handlePDFUpload = async (e) => {
    if (e.target.files && e.target.files[0]) {
      setUploadStatus("Scanning PDF...");
      setIsProcessing(true);
      setScreeningError(null);
      try {
        const data = await LisService.uploadPdf(e.target.files[0]);
        setRows((prev) =>
          prev.map((r) => ({
            ...r,
            value: data[r.key] !== undefined ? String(data[r.key]) : r.value,
          }))
        );
        setUploadStatus("Extraction Complete. Please verify values below.");
        setActiveTab("manual");
      } catch (err) {
        setUploadStatus("Error reading PDF.");
      } finally {
        setIsProcessing(false);
      }
    }
  };

  const checkExistingConsent = async () => {
    if (!patient.id) return false;
    try {
      const status = await ConsentService.getStatus(patient.id);
      if (status.hasConsent) {
        setConsentId(status.consentId);
        setHasValidConsent(true);
        return true;
      }
    } catch (err) {
      console.error("Failed to check consent:", err);
    }
    return false;
  };

  const handleConsentCaptured = async (consentData) => {
    const result = await ConsentService.record(patient.id, consentData);
    setConsentId(result.id);
    setHasValidConsent(true);
    setShowConsentCapture(false);
    // Automatically run screening after consent
    runScreeningWithConsent(result.id);
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

    // Check for existing consent
    const hasConsent = await checkExistingConsent();
    
    if (hasConsent) {
      // Run with existing consent
      runScreeningWithConsent(consentId);
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
    setRandomProfile(null);
  };

  // Generate random test data for testing model accuracy
  const generateRandomData = (profileType = null) => {
    // Randomly select profile if not specified
    const profiles = Object.keys(CBC_PROFILES);
    const selectedType = profileType || profiles[Math.floor(Math.random() * profiles.length)];
    const profile = CBC_PROFILES[selectedType];

    // Generate CBC data based on patient sex
    const cbcData = profile.getData(patient.sex);

    // Update rows with generated values
    setRows((prev) =>
      prev.map((r) => ({
        ...r,
        value: cbcData[r.key] !== undefined ? String(cbcData[r.key]) : r.value,
      }))
    );

    // Generate random patient data
    const firstNames = ["James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda", "William", "Elizabeth"];
    const lastNames = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"];
    const randomName = `${lastNames[Math.floor(Math.random() * lastNames.length)]}, ${firstNames[Math.floor(Math.random() * firstNames.length)]}`;
    const randomAge = Math.floor(Math.random() * 60) + 20; // 20-80 years
    const randomId = `PT-${Date.now().toString().slice(-6)}-${Math.floor(Math.random() * 100)}`;

    setPatient((prev) => ({
      ...prev,
      name: randomName,
      age: randomAge,
      id: randomId,
      // Preserve user's lab_code if available, otherwise generate random
      labId: user?.lab_code || `LAB-${new Date().getFullYear()}-${Math.floor(Math.random() * 1000).toString().padStart(3, '0')}`,
      // Preserve doctor for DOCTOR role
      referringDoctor: user?.role === Role.DOCTOR ? (user?.doctor_code || prev.referringDoctor) : prev.referringDoctor,
    }));

    setRandomProfile(profile);
    setHasValidConsent(false);
    setConsentId(null);
    setResult(null);
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
          <div className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-white rounded-xl shadow-2xl animate-in fade-in zoom-in duration-200">
            {/* Close Button */}
            <button
              onClick={() => setShowConsentCapture(false)}
              className="absolute top-4 right-4 p-1 rounded-lg hover:bg-slate-100 z-10"
            >
              <X className="h-5 w-5 text-slate-500" />
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
          <section className="bg-white border border-slate-300 rounded-sm shadow-sm overflow-hidden">
            <div className="bg-slate-50 border-b border-slate-200 px-4 py-3 flex items-center justify-between">
              <h3 className="font-bold text-slate-700 text-sm uppercase tracking-wide">Patient Registration</h3>
              <span className="text-xs font-mono text-slate-500">{patient.labId}</span>
            </div>
            <div className="p-4 grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <label className="block text-xs font-semibold text-slate-500 mb-1">Full Name</label>
                <input
                  data-testid="patient-name-input"
                  type="text"
                  className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm focus:ring-1 focus:ring-teal-500 focus:border-teal-500 bg-white text-black"
                  placeholder="Doe, Jane"
                  value={patient.name}
                  onChange={(e) => setPatient({ ...patient, name: e.target.value })}
                />
              </div>
              {/* Referring Doctor - Only show for LAB role, auto-set for DOCTOR role */}
              {user?.role === Role.LAB ? (
                <div className="col-span-2">
                  <label className="block text-xs font-semibold text-slate-500 mb-1">Referring Doctor</label>
                  <div className="relative">
                    <Stethoscope className="w-4 h-4 absolute left-2 top-2 text-slate-400" />
                    <select
                      data-testid="referring-doctor-select"
                      className="w-full border border-slate-300 rounded pl-8 pr-2 py-1.5 text-sm bg-white text-black"
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
                  <label className="block text-xs font-semibold text-slate-500 mb-1">Referring Doctor</label>
                  <div className="flex items-center p-2 bg-blue-50 border border-blue-100 rounded text-sm text-blue-700">
                    <Stethoscope className="h-4 w-4 mr-2" />
                    <span>Dr. {user?.name} (You)</span>
                  </div>
                </div>
              ) : null}
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Age</label>
                <input
                  data-testid="patient-age-input"
                  type="number"
                  className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm bg-white text-black"
                  value={patient.age || ""}
                  onChange={(e) => setPatient({ ...patient, age: parseInt(e.target.value || "0", 10) })}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Sex</label>
                <select
                  data-testid="patient-sex-select"
                  className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm bg-white"
                  value={patient.sex}
                  onChange={(e) => setPatient({ ...patient, sex: e.target.value })}
                >
                  <option value="F">Female</option>
                  <option value="M">Male</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Patient ID</label>
                <input
                  data-testid="patient-id-input"
                  type="text"
                  className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm font-mono bg-white text-black"
                  value={patient.id}
                  onChange={(e) => {
                    setPatient({ ...patient, id: e.target.value });
                    setHasValidConsent(false);
                    setConsentId(null);
                  }}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Date</label>
                <input
                  data-testid="patient-date-input"
                  type="date"
                  className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm bg-white text-black"
                  value={patient.date}
                  onChange={(e) => setPatient({ ...patient, date: e.target.value })}
                />
              </div>
              
              {/* Consent Status Indicator */}
              {patient.id && (
                <div className="col-span-2">
                  {hasValidConsent ? (
                    <div className="flex items-center p-2 bg-green-50 border border-green-100 rounded text-sm text-green-700">
                      <CheckCircle className="h-4 w-4 mr-2" />
                      <span>Consent recorded (ID: {consentId?.slice(0, 8)}...)</span>
                    </div>
                  ) : (
                    <div className="flex items-center p-2 bg-slate-50 border border-slate-200 rounded text-sm text-slate-600">
                      <FileCheck className="h-4 w-4 mr-2" />
                      <span>Consent will be captured before screening</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>

          <div className="bg-white border border-slate-300 rounded-sm shadow-sm overflow-hidden">
            <div className="border-b border-slate-200 flex">
              <button
                data-testid="tab-manual"
                onClick={() => setActiveTab("manual")}
                className={`flex-1 py-3 text-sm font-medium flex items-center justify-center ${
                  activeTab === "manual" ? "text-teal-700 border-b-2 border-teal-600 bg-teal-50/50" : "text-slate-500 hover:bg-slate-50"
                }`}
              >
                <FileText className="w-4 h-4 mr-2" />
                Manual Entry
              </button>
              <button
                data-testid="tab-pdf"
                onClick={() => setActiveTab("pdf")}
                className={`flex-1 py-3 text-sm font-medium flex items-center justify-center ${
                  activeTab === "pdf" ? "text-teal-700 border-b-2 border-teal-600 bg-teal-50/50" : "text-slate-500 hover:bg-slate-50"
                }`}
              >
                <Upload className="w-4 h-4 mr-2" />
                Import PDF Report
              </button>
            </div>

            {activeTab === "pdf" && (
              <div className="p-6 bg-slate-50">
                <div className="border-2 border-dashed border-slate-300 rounded-lg p-8 text-center hover:border-teal-500 transition-colors bg-white cursor-pointer relative">
                  <input data-testid="pdf-file-input" type="file" accept=".pdf" onChange={handlePDFUpload} className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" />
                  <Upload className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                  <p className="text-sm text-slate-600 font-medium">Click to upload Hospital CBC Report (PDF)</p>
                  <p className="text-xs text-slate-400 mt-1">Supports Siemens, Abbott, Roche formats</p>
                </div>
                {uploadStatus && (
                  <div data-testid="pdf-upload-status" className="mt-4 flex items-center text-sm text-teal-700 bg-teal-50 border border-teal-100 p-2 rounded">
                    {isProcessing && <div className="animate-spin h-3 w-3 border-2 border-teal-600 border-t-transparent rounded-full mr-2" />}
                    {uploadStatus}
                  </div>
                )}
              </div>
            )}

            <div className={`${activeTab === "manual" ? "block" : "hidden"}`}>
              <CBCTable rows={rows} patientSex={patient.sex} onValueChange={handleCBCChange} />
            </div>

            {screeningError && (
              <div data-testid="screening-error" className="px-4 py-3 bg-red-50 border-t border-red-100 text-sm text-red-700">
                {screeningError}
              </div>
            )}

            {/* Random Data Indicator */}
            {randomProfile && (
              <div className={`px-4 py-3 border-t flex items-center gap-3 ${
                randomProfile.color === "green" ? "bg-green-50 border-green-100" :
                randomProfile.color === "amber" ? "bg-amber-50 border-amber-100" :
                "bg-red-50 border-red-100"
              }`}>
                <Info className={`w-5 h-5 flex-shrink-0 ${
                  randomProfile.color === "green" ? "text-green-600" :
                  randomProfile.color === "amber" ? "text-amber-600" :
                  "text-red-600"
                }`} />
                <div className="flex-1">
                  <p className={`text-sm font-semibold ${
                    randomProfile.color === "green" ? "text-green-800" :
                    randomProfile.color === "amber" ? "text-amber-800" :
                    "text-red-800"
                  }`}>
                    Test Data: {randomProfile.label} Profile
                  </p>
                  <p className={`text-xs ${
                    randomProfile.color === "green" ? "text-green-600" :
                    randomProfile.color === "amber" ? "text-amber-600" :
                    "text-red-600"
                  }`}>
                    {randomProfile.expectedB12}
                  </p>
                </div>
                <span className={`px-2 py-1 rounded-full text-xs font-bold ${
                  randomProfile.color === "green" ? "bg-green-200 text-green-800" :
                  randomProfile.color === "amber" ? "bg-amber-200 text-amber-800" :
                  "bg-red-200 text-red-800"
                }`}>
                  Expected: {randomProfile.label}
                </span>
              </div>
            )}

            <div className="p-4 bg-slate-50 border-t border-slate-200 flex justify-between items-center gap-2">
              <div className="flex items-center gap-2">
                <button data-testid="reset-form-button" onClick={resetForm} className="px-4 py-2 border border-slate-300 rounded bg-white text-slate-600 text-sm font-medium hover:bg-slate-50 flex items-center">
                  <RotateCcw className="w-4 h-4 mr-2" /> Reset
                </button>

                {/* Randomize Dropdown */}
                <div className="relative group">
                  <button
                    data-testid="randomize-button"
                    onClick={() => generateRandomData()}
                    className="px-4 py-2 border border-violet-300 rounded bg-violet-50 text-violet-700 text-sm font-medium hover:bg-violet-100 flex items-center"
                  >
                    <Shuffle className="w-4 h-4 mr-2" /> Randomize
                  </button>
                  <div className="absolute left-0 top-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10 min-w-[200px]">
                    <p className="px-3 py-2 text-xs font-semibold text-slate-400 uppercase border-b">Select Profile</p>
                    <button
                      onClick={() => generateRandomData("normal")}
                      className="w-full px-3 py-2 text-sm text-left hover:bg-green-50 flex items-center gap-2"
                    >
                      <span className="w-2 h-2 rounded-full bg-green-500"></span>
                      Normal CBC
                    </button>
                    <button
                      onClick={() => generateRandomData("borderline")}
                      className="w-full px-3 py-2 text-sm text-left hover:bg-amber-50 flex items-center gap-2"
                    >
                      <span className="w-2 h-2 rounded-full bg-amber-500"></span>
                      Borderline B12
                    </button>
                    <button
                      onClick={() => generateRandomData("deficient")}
                      className="w-full px-3 py-2 text-sm text-left hover:bg-red-50 flex items-center gap-2"
                    >
                      <span className="w-2 h-2 rounded-full bg-red-500"></span>
                      B12 Deficient
                    </button>
                  </div>
                </div>
              </div>

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
            <div className="h-full min-h-[500px] border-2 border-dashed border-slate-300 rounded-sm bg-slate-50 flex flex-col items-center justify-center text-slate-400" data-testid="no-results-empty">
              <div className="bg-white p-6 rounded-full shadow-sm mb-4">
                <Activity className="w-12 h-12 text-slate-300" />
              </div>
              <h3 className="text-lg font-medium text-slate-500">No Analysis Results Yet</h3>
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
