import React, { useEffect, useState } from "react";
import { LisService } from "../services/api";
import { ScreeningLabel, Role } from "../types";
import { Search, Filter, FileText, Download, Eye, Calendar, User, ArrowLeft, X, Loader2, CheckCircle2, MessageSquare } from "lucide-react";
import { generateReport, buildCbcRowsFromSnapshot, buildResultFromScreening } from "@/lib/generateReport";
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";

const PAGE_SIZE = 50;

const PatientRecords = ({ doctorId, doctorName, onBack, userRole }) => {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [detailRecord, setDetailRecord] = useState(null);   // full screening for the drawer
  const [detailLoading, setDetailLoading] = useState(false);
  const [downloadingId, setDownloadingId] = useState(null); // tracks which row is downloading
  // 3.3 Review workflow
  const [reviewNote, setReviewNote] = useState("");
  const [reviewing, setReviewing] = useState(false);
  // 3.4 Trend
  const [trend, setTrend] = useState(null);
  const [trendLoading, setTrendLoading] = useState(false);

  useEffect(() => {
    const fetchRecords = async () => {
      setLoading(true);
      try {
        const data = await LisService.getPatientRecords(doctorId, undefined, page, PAGE_SIZE);
        setRecords(data.results ?? data);
        setTotalCount(data.count ?? (data.results ?? data).length);
      } catch (e) {
        console.error("Failed to load records", e);
      } finally {
        setLoading(false);
      }
    };
    fetchRecords();
  }, [doctorId, page]);

  const handleViewDetails = async (record) => {
    setDetailLoading(true);
    setDetailRecord(null);
    setTrend(null);
    setReviewNote("");
    try {
      const full = await LisService.getScreening(record.id);
      setDetailRecord(full);
      // Load trend for this patient
      if (record.patientId) {
        setTrendLoading(true);
        try {
          const trendData = await LisService.getPatientTrend(record.patientId);
          setTrend(trendData.trend || []);
        } catch {
          setTrend([]);
        } finally {
          setTrendLoading(false);
        }
      }
    } catch (e) {
      console.error("Failed to load screening detail", e);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleMarkReviewed = async () => {
    if (!detailRecord) return;
    setReviewing(true);
    try {
      const result = await LisService.reviewScreening(detailRecord.id, reviewNote);
      setDetailRecord((prev) => ({ ...prev, ...result }));
      // Also update the row in the table
      setRecords((prev) =>
        prev.map((r) => r.id === detailRecord.id ? { ...r, is_reviewed: true } : r)
      );
    } catch (e) {
      console.error("Review failed", e);
    } finally {
      setReviewing(false);
    }
  };

  const handleDownload = async (record) => {
    setDownloadingId(record.id);
    try {
      const full = await LisService.getScreening(record.id);
      const patient = {
        name:  full.patient_name || record.name,
        id:    full.patient_id   || record.patientId,
        age:   full.cbc_snapshot?.Age ?? record.age,
        sex:   full.cbc_snapshot?.Sex ?? record.sex,
        date:  record.date,
        labId: full.lab_name    || record.labId,
      };
      const result  = buildResultFromScreening(full);
      const cbcRows = buildCbcRowsFromSnapshot(full.cbc_snapshot || {});
      const doc = await generateReport(patient, result, cbcRows);
      doc.save(`ClinomicLabs_Report_${patient.id}.pdf`);
    } catch (e) {
      console.error("Failed to generate report", e);
    } finally {
      setDownloadingId(null);
    }
  };

  // Reset to page 1 when search term changes
  const handleSearch = (value) => {
    setSearchTerm(value);
    setPage(1);
  };

  const filteredRecords = records.filter((r) =>
    String(r.name || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
    String(r.patientId || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
    String(r.labId || "").toLowerCase().includes(searchTerm.toLowerCase())
  );

  const getStatusBadge = (status) => {
    switch (status) {
      case ScreeningLabel.NORMAL:
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 border border-green-200 dark:border-green-800">Normal</span>;
      case ScreeningLabel.BORDERLINE:
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-800">Borderline</span>;
      case ScreeningLabel.DEFICIENT:
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300 border border-red-200 dark:border-red-800">Deficient</span>;
      default:
        return null;
    }
  };

  return (
    <div className="space-y-6" data-testid="patient-records">
      {onBack && (
        <button data-testid="back-to-doctors" onClick={onBack} className="flex items-center text-sm text-slate-500 dark:text-slate-400 hover:text-teal-600 mb-2 transition-colors">
          <ArrowLeft className="w-4 h-4 mr-1" /> Back to Doctor Registry
        </button>
      )}

      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100">{doctorName ? `Records: ${doctorName}` : "Patient Records"}</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">History of screening results and reports</p>
        </div>
        <div className="flex items-center space-x-2 w-full sm:w-auto">
          <div className="relative flex-1 sm:flex-none sm:w-64">
            <Search className="w-4 h-4 absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400 dark:text-slate-500" />
            <input
              data-testid="records-search-input"
              type="text"
              placeholder="Search Name, ID, or Lab Ref..."
              value={searchTerm}
              onChange={(e) => handleSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm border border-slate-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-1 focus:ring-teal-500 bg-white dark:bg-slate-800 shadow-sm"
            />
          </div>
          <button data-testid="records-filter-button" aria-label="Filter records" className="p-2 border border-slate-300 dark:border-slate-600 rounded-md bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300">
            <Filter className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-sm shadow-sm overflow-hidden" data-testid="records-table">
        {loading ? (
          <div className="p-12 text-center text-slate-500 dark:text-slate-400" data-testid="records-loading">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-teal-600 mx-auto mb-3" />
            Loading records...
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-700 text-sm">
              <thead className="bg-slate-50 dark:bg-slate-800">
                <tr>
                  <th className="px-6 py-3 text-left font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider text-xs w-32">Patient ID</th>
                  <th className="px-6 py-3 text-left font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider text-xs">Patient Details</th>
                  <th className="px-6 py-3 text-left font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider text-xs">Lab Ref / Date</th>
                  <th className="px-6 py-3 text-center font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider text-xs">Screening Result</th>
                  <th className="px-6 py-3 text-center font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider text-xs">Review</th>
                  <th className="px-6 py-3 text-right font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider text-xs">Actions</th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-slate-900 divide-y divide-slate-100 dark:divide-slate-700">
                {filteredRecords.length > 0 ? (
                  filteredRecords.map((record) => (
                    <tr key={record.id} className="hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors group" data-testid={`record-row-${record.id}`}
                    >
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm font-mono font-medium text-slate-700 dark:text-slate-300">{record.patientId}</div>
                        <div className="text-xs text-slate-400 dark:text-slate-500">Case: {record.id}</div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center">
                          <div className="h-8 w-8 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-500 dark:text-slate-400 mr-3">
                            <User className="w-4 h-4" />
                          </div>
                          <div>
                            <div className="text-sm font-bold text-slate-900 dark:text-slate-100">{record.name || ""}</div>
                            <div className="text-xs text-slate-500 dark:text-slate-400">{record.age} Y / {record.sex}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="text-sm text-slate-600 dark:text-slate-300 font-mono">{record.labId}</div>
                        <div className="flex items-center text-xs text-slate-400 dark:text-slate-500 mt-0.5">
                          <Calendar className="w-3 h-3 mr-1" />
                          {record.date}
                        </div>
                      </td>
                      <td className="px-6 py-4 text-center">{getStatusBadge(record.result)}</td>
                      <td className="px-6 py-4 text-center">
                        {record.is_reviewed
                          ? <CheckCircle2 className="h-4 w-4 text-green-500 mx-auto" title="Reviewed" />
                          : <span className="text-xs text-slate-300">—</span>}
                      </td>
                      <td className="px-6 py-4 text-right whitespace-nowrap text-sm font-medium">
                        <div className="flex justify-end space-x-2">
                          <button
                            data-testid={`record-view-${record.id}`}
                            onClick={() => handleViewDetails(record)}
                            className="text-slate-400 dark:text-slate-500 hover:text-teal-600 p-1 rounded hover:bg-teal-50 transition-colors"
                            aria-label="View details"
                            title="View Details"
                          >
                            <Eye className="w-4 h-4" />
                          </button>
                          <button
                            data-testid={`record-download-${record.id}`}
                            onClick={() => handleDownload(record)}
                            disabled={downloadingId === record.id}
                            className="text-slate-400 dark:text-slate-500 hover:text-teal-600 p-1 rounded hover:bg-teal-50 transition-colors disabled:opacity-40"
                            aria-label="Download report"
                            title="Download Report"
                          >
                            {downloadingId === record.id
                              ? <Loader2 className="w-4 h-4 animate-spin" />
                              : <Download className="w-4 h-4" />}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6} className="px-6 py-10 text-center text-slate-400 dark:text-slate-500" data-testid="no-records">
                      <FileText className="w-10 h-10 mx-auto mb-2 text-slate-300" />
                      <p>No records found matching "{searchTerm}"</p>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
        <div className="px-6 py-3 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-xs text-slate-500 dark:text-slate-400 flex justify-between items-center">
          <span data-testid="records-total">Total Records: {totalCount} (Page {page} of {Math.max(1, Math.ceil(totalCount / PAGE_SIZE))})</span>
          <div className="flex space-x-2">
            <button
              className="px-2 py-1 border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
              disabled={page <= 1 || loading}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </button>
            <button
              className="px-2 py-1 border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
              disabled={page >= Math.ceil(totalCount / PAGE_SIZE) || loading}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        </div>
      </div>
      {/* ── Detail Drawer ─────────────────────────────────────────────── */}
      {(detailLoading || detailRecord) && (
        <div className="fixed inset-0 z-40 flex justify-end" aria-modal="true">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setDetailRecord(null)}
          />
          {/* Panel */}
          <div className="relative z-50 w-full max-w-lg bg-white dark:bg-slate-900 shadow-xl overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800">
              <h3 className="text-base font-bold text-slate-800 dark:text-slate-100">Screening Details</h3>
              <button
                onClick={() => setDetailRecord(null)}
                aria-label="Close details panel"
                className="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-500 dark:text-slate-400"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {detailLoading ? (
              <div className="flex items-center justify-center py-24">
                <Loader2 className="w-8 h-8 animate-spin text-teal-600" />
              </div>
            ) : detailRecord && (
              <div className="p-6 space-y-5 text-sm">
                {/* Patient */}
                <section>
                  <p className="text-xs font-bold uppercase text-slate-400 dark:text-slate-500 mb-2">Patient</p>
                  <div className="grid grid-cols-2 gap-2">
                    <div><span className="text-slate-500 dark:text-slate-400">Name</span><p className="font-medium text-slate-800 dark:text-slate-100">{detailRecord.patient_name || "—"}</p></div>
                    <div><span className="text-slate-500 dark:text-slate-400">ID</span><p className="font-mono font-medium text-slate-800 dark:text-slate-100">{detailRecord.patient_id}</p></div>
                    <div><span className="text-slate-500 dark:text-slate-400">Lab</span><p className="font-medium text-slate-800 dark:text-slate-100">{detailRecord.lab_name || "—"}</p></div>
                    <div><span className="text-slate-500 dark:text-slate-400">Doctor</span><p className="font-medium text-slate-800 dark:text-slate-100">{detailRecord.doctor_name || "—"}</p></div>
                    <div><span className="text-slate-500 dark:text-slate-400">Date</span><p className="font-medium text-slate-800 dark:text-slate-100">{new Date(detailRecord.created_at).toLocaleDateString()}</p></div>
                    <div><span className="text-slate-500 dark:text-slate-400">Model</span><p className="font-mono text-slate-800 dark:text-slate-100">{detailRecord.model_version}</p></div>
                  </div>
                </section>

                {/* Result */}
                <section>
                  <p className="text-xs font-bold uppercase text-slate-400 dark:text-slate-500 mb-2">Result</p>
                  <p className="font-bold text-slate-800 dark:text-slate-100">{detailRecord.label_text}</p>
                  {detailRecord.probabilities && (
                    <div className="mt-1 flex gap-3 text-xs">
                      <span className="text-green-700 dark:text-green-400">Normal {(detailRecord.probabilities.normal * 100).toFixed(1)}%</span>
                      <span className="text-amber-700 dark:text-amber-400">Borderline {(detailRecord.probabilities.borderline * 100).toFixed(1)}%</span>
                      <span className="text-red-700 dark:text-red-400">Deficient {(detailRecord.probabilities.deficient * 100).toFixed(1)}%</span>
                    </div>
                  )}
                </section>

                {/* Indices */}
                {detailRecord.indices && (
                  <section>
                    <p className="text-xs font-bold uppercase text-slate-400 dark:text-slate-500 mb-2">Hematological Indices</p>
                    <table className="w-full text-xs border border-slate-200 dark:border-slate-700 rounded">
                      <thead className="bg-slate-50 dark:bg-slate-800">
                        <tr>
                          <th className="px-3 py-1.5 text-left text-slate-500 dark:text-slate-400 font-medium">Index</th>
                          <th className="px-3 py-1.5 text-right text-slate-500 dark:text-slate-400 font-medium">Value</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                        <tr><td className="px-3 py-1.5">Mentzer</td><td className="px-3 py-1.5 text-right font-mono">{detailRecord.indices.mentzer}</td></tr>
                        <tr><td className="px-3 py-1.5">Green &amp; King</td><td className="px-3 py-1.5 text-right font-mono">{detailRecord.indices.greenKing}</td></tr>
                        <tr><td className="px-3 py-1.5">NLR</td><td className="px-3 py-1.5 text-right font-mono">{detailRecord.indices.nlr}</td></tr>
                      </tbody>
                    </table>
                  </section>
                )}

                {/* Rules fired */}
                {detailRecord.rules_fired?.length > 0 && (
                  <section>
                    <p className="text-xs font-bold uppercase text-slate-400 dark:text-slate-500 mb-2">Clinical Interpretation</p>
                    <ul className="list-disc list-inside space-y-1 text-slate-700 dark:text-slate-300">
                      {detailRecord.rules_fired.map((r, i) => <li key={i}>{r}</li>)}
                    </ul>
                  </section>
                )}

                {/* 3.4 — Trend chart */}
                {(trendLoading || (trend && trend.length > 1)) && (
                  <section>
                    <p className="text-xs font-bold uppercase text-slate-400 dark:text-slate-500 mb-2">Patient CBC Trend</p>
                    {trendLoading ? (
                      <div className="flex items-center justify-center h-32">
                        <Loader2 className="w-5 h-5 animate-spin text-teal-500" />
                      </div>
                    ) : (
                      <ResponsiveContainer width="100%" height={180}>
                        <LineChart data={trend} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
                          <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                          <YAxis tick={{ fontSize: 10 }} width={28} />
                          <Tooltip contentStyle={{ fontSize: 11 }} />
                          <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
                          <Line type="monotone" dataKey="MCV"  stroke="#6366f1" dot={false} strokeWidth={1.5} />
                          <Line type="monotone" dataKey="MCH"  stroke="#0ea5e9" dot={false} strokeWidth={1.5} />
                          <Line type="monotone" dataKey="Hgb"  stroke="#10b981" dot={false} strokeWidth={1.5} />
                          <Line type="monotone" dataKey="RBC"  stroke="#f59e0b" dot={false} strokeWidth={1.5} />
                        </LineChart>
                      </ResponsiveContainer>
                    )}
                  </section>
                )}

                {/* 3.3 — Doctor review */}
                <section>
                  <p className="text-xs font-bold uppercase text-slate-400 dark:text-slate-500 mb-2">Clinical Review</p>
                  {detailRecord.is_reviewed ? (
                    <div className="flex items-start gap-2 p-3 rounded-lg bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800">
                      <CheckCircle2 className="h-4 w-4 text-green-600 mt-0.5 shrink-0" />
                      <div className="text-xs text-green-800 dark:text-green-300">
                        <p className="font-semibold">Reviewed by {detailRecord.reviewed_by}</p>
                        {detailRecord.reviewed_at && (
                          <p className="text-green-600 mt-0.5">{new Date(detailRecord.reviewed_at).toLocaleString()}</p>
                        )}
                        {detailRecord.clinical_note && (
                          <p className="mt-1 text-green-800 dark:text-green-300 italic">"{detailRecord.clinical_note}"</p>
                        )}
                      </div>
                    </div>
                  ) : (
                    userRole === Role.DOCTOR && (
                      <div className="space-y-2">
                        <textarea
                          rows={2}
                          placeholder="Optional clinical note..."
                          value={reviewNote}
                          onChange={(e) => setReviewNote(e.target.value)}
                          className="w-full text-xs border border-slate-300 dark:border-slate-600 rounded px-2.5 py-2 focus:outline-none focus:ring-1 focus:ring-teal-500 resize-none bg-white dark:bg-slate-800"
                        />
                        <button
                          onClick={handleMarkReviewed}
                          disabled={reviewing}
                          className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded text-sm font-medium disabled:opacity-50"
                        >
                          {reviewing
                            ? <Loader2 className="w-4 h-4 animate-spin" />
                            : <MessageSquare className="w-4 h-4" />}
                          Mark as Reviewed
                        </button>
                      </div>
                    )
                  )}
                </section>

                {/* Download from drawer */}
                <button
                  onClick={() => handleDownload({ id: detailRecord.id, ...detailRecord })}
                  disabled={downloadingId === detailRecord.id}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-800 text-white rounded text-sm font-medium disabled:opacity-50"
                >
                  {downloadingId === detailRecord.id
                    ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <Download className="w-4 h-4" />}
                  Download PDF Report
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default PatientRecords;
