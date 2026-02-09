import React, { useState } from 'react';
import { PatientData, CBCRow, ScreeningResult } from '../types';
import { INITIAL_CBC_ROWS } from '../constants';
import CBCTable from '../components/CBCTable';
import ResultPanel from '../components/ResultPanel';
import { LisService, AuthService } from "../services/api";
import { Upload, FileText, Play, RotateCcw, Activity, Stethoscope } from 'lucide-react';

const UserWorkspace: React.FC = () => {
  const [patient, setPatient] = useState<PatientData>({
    id: '',
    name: '',
    age: 0,
    sex: 'F',
    date: new Date().toISOString().split('T')[0],
    labId: 'LAB-2024-001',
    referringDoctor: ''
  });

  const [rows, setRows] = useState<CBCRow[]>(INITIAL_CBC_ROWS);
  const [activeTab, setActiveTab] = useState<'manual' | 'pdf'>('manual');
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState<ScreeningResult | null>(null);
  const [uploadStatus, setUploadStatus] = useState<string>('');

  const handleCBCChange = (key: string, value: string) => {
    setRows(prev => prev.map(r => r.key === key ? { ...r, value } : r));
  };

  const handlePDFUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setUploadStatus('Scanning PDF...');
      setIsProcessing(true);
      try {
        const data = await LisService.uploadPdf(e.target.files[0]);
        // Map mock data to rows
        setRows(prev => prev.map(r => ({
          ...r,
          value: data[r.key] !== undefined ? data[r.key].toString() : r.value
        })));
        setUploadStatus('Extraction Complete. Please verify values below.');
        setActiveTab('manual'); // Switch to view data
      } catch (err) {
        setUploadStatus('Error reading PDF.');
      } finally {
        setIsProcessing(false);
      }
    }
  };

  const runScreening = async () => {
    setIsProcessing(true);
    try {
      // Convert rows to key-value record for API
      const cbcData: Record<string, number> = {};
      rows.forEach(r => {
        const val = parseFloat(r.value);
        if (!isNaN(val)) cbcData[r.key] = val;
      });

      const res = await LisService.predictB12(cbcData, patient);
      setResult(res);
    } catch (err: any) {
      console.error("Screening Error:", err);
      if (err.response) {
        console.error("Server Response:", err.response.data);
      }
      setResult(null); // Clear previous result
      // Temporarily use result panel to show error if possible, or just log for now.
    } finally {
      setIsProcessing(false);
    }
  };

  const resetForm = () => {
    setResult(null);
    setRows(INITIAL_CBC_ROWS.map(r => ({ ...r, value: '' })));
    setPatient(prev => ({ ...prev, id: '' }));
  };



  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        {/* LEFT COLUMN: Input */}
        <div className="xl:col-span-5 space-y-6">

          {/* Patient Registration */}
          <section className="bg-white border border-slate-300 rounded-sm shadow-sm overflow-hidden">
            <div className="bg-slate-50 border-b border-slate-200 px-4 py-3 flex items-center justify-between">
              <h3 className="font-bold text-slate-700 text-sm uppercase tracking-wide">Patient Registration</h3>
              <span className="text-xs font-mono text-slate-500">{patient.labId}</span>
            </div>
            <div className="p-4 grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <label className="block text-xs font-semibold text-slate-500 mb-1">Full Name</label>
                <input
                  type="text"
                  className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm focus:ring-1 focus:ring-teal-500 focus:border-teal-500 bg-white text-black"
                  placeholder="Doe, Jane"
                  value={patient.name}
                  onChange={e => setPatient({ ...patient, name: e.target.value })}
                />
              </div>
              <div className="col-span-2">
                <label className="block text-xs font-semibold text-slate-500 mb-1">Referring Doctor</label>
                <div className="relative">
                  <Stethoscope className="w-4 h-4 absolute left-2 top-2 text-slate-400" />
                  <select
                    className="w-full border border-slate-300 rounded pl-8 pr-2 py-1.5 text-sm bg-white text-black"
                    value={patient.referringDoctor}
                    onChange={e => setPatient({ ...patient, referringDoctor: e.target.value })}
                  >
                    <option value="">Select Physician...</option>
                    <option value="D201">Dr. Sarah Chen (Hematology)</option>
                    <option value="D202">Dr. Michael Ross (GP)</option>
                    <option value="D205">Dr. Robert Chase (Critical Care)</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Age</label>
                <input
                  type="number"
                  className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm bg-white text-black"
                  value={patient.age || ''}
                  onChange={e => setPatient({ ...patient, age: parseInt(e.target.value) })}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Sex</label>
                <select
                  className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm bg-white"
                  value={patient.sex}
                  onChange={e => setPatient({ ...patient, sex: e.target.value as 'M' | 'F' })}
                >
                  <option value="F">Female</option>
                  <option value="M">Male</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Patient ID</label>
                <input
                  type="text"
                  className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm font-mono bg-white text-black"
                  value={patient.id}
                  onChange={e => setPatient({ ...patient, id: e.target.value })}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Date</label>
                <input
                  type="date"
                  className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm bg-white text-black"
                  value={patient.date}
                  onChange={e => setPatient({ ...patient, date: e.target.value })}
                />
              </div>
            </div>
          </section>

          {/* Data Entry Mode Selection */}
          <div className="bg-white border border-slate-300 rounded-sm shadow-sm overflow-hidden">
            <div className="border-b border-slate-200 flex">
              <button
                onClick={() => setActiveTab('manual')}
                className={`flex-1 py-3 text-sm font-medium flex items-center justify-center ${activeTab === 'manual' ? 'text-teal-700 border-b-2 border-teal-600 bg-teal-50/50' : 'text-slate-500 hover:bg-slate-50'}`}
              >
                <FileText className="w-4 h-4 mr-2" />
                Manual Entry
              </button>
              <button
                onClick={() => setActiveTab('pdf')}
                className={`flex-1 py-3 text-sm font-medium flex items-center justify-center ${activeTab === 'pdf' ? 'text-teal-700 border-b-2 border-teal-600 bg-teal-50/50' : 'text-slate-500 hover:bg-slate-50'}`}
              >
                <Upload className="w-4 h-4 mr-2" />
                Import PDF Report
              </button>
            </div>

            {activeTab === 'pdf' && (
              <div className="p-6 bg-slate-50">
                <div className="border-2 border-dashed border-slate-300 rounded-lg p-8 text-center hover:border-teal-500 transition-colors bg-white cursor-pointer relative">
                  <input
                    type="file"
                    accept=".pdf"
                    onChange={handlePDFUpload}
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                  />
                  <Upload className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                  <p className="text-sm text-slate-600 font-medium">Click to upload Hospital CBC Report (PDF)</p>
                  <p className="text-xs text-slate-400 mt-1">Supports Siemens, Abbott, Roche formats</p>
                </div>
                {uploadStatus && (
                  <div className="mt-4 flex items-center text-sm text-teal-700 bg-teal-50 border border-teal-100 p-2 rounded">
                    {isProcessing && <div className="animate-spin h-3 w-3 border-2 border-teal-600 border-t-transparent rounded-full mr-2"></div>}
                    {uploadStatus}
                  </div>
                )}
              </div>
            )}

            <div className={`${activeTab === 'manual' ? 'block' : 'hidden'}`}>
              <CBCTable
                rows={rows}
                patientSex={patient.sex}
                onValueChange={handleCBCChange}
              />
            </div>

            <div className="p-4 bg-slate-50 border-t border-slate-200 flex justify-between">
              <button
                onClick={resetForm}
                className="px-4 py-2 border border-slate-300 rounded bg-white text-slate-600 text-sm font-medium hover:bg-slate-50 flex items-center"
              >
                <RotateCcw className="w-4 h-4 mr-2" /> Reset
              </button>
              <button
                onClick={runScreening}
                disabled={isProcessing}
                className="px-6 py-2 bg-teal-700 rounded text-white text-sm font-bold hover:bg-teal-800 shadow-sm flex items-center disabled:opacity-50"
              >
                {isProcessing ? 'Analyzing...' : (
                  <>
                    <Play className="w-4 h-4 mr-2 fill-current" /> Run B12 Screening
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Results */}
        <div className="xl:col-span-7">
          {result ? (
            <ResultPanel
              result={result}
              patient={patient}
              cbcRows={rows}
            />
          ) : (
            <div className="h-full min-h-[500px] border-2 border-dashed border-slate-300 rounded-sm bg-slate-50 flex flex-col items-center justify-center text-slate-400">
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
  );
};

export default UserWorkspace;