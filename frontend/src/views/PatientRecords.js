import React, { useEffect, useState } from "react";
import { LisService } from "../services/api";
import { ScreeningLabel } from "../types";
import { Search, Filter, FileText, Download, Eye, Calendar, User, ArrowLeft, Loader2, CheckCircle2 } from "lucide-react";
import { generateReport, buildCbcRowsFromSnapshot, buildResultFromScreening } from "@/lib/generateReport";
import ScreeningDetailDrawer from "../components/ScreeningDetailDrawer";

const PAGE_SIZE = 50;

const PatientRecords = ({ doctorId, doctorName, onBack, userRole }) => {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [detailScreeningId, setDetailScreeningId] = useState(null);
  const [downloadingId, setDownloadingId] = useState(null); // tracks which row is downloading

  // Increment to force a re-fetch (e.g. after navigating back from screening)
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    // Cancellation flag — if the deps change (page/doctor) before this fetch
    // resolves, ignore its result so the previous page's data doesn't
    // overwrite the new page's data on slow networks.
    let cancelled = false;
    const fetchRecords = async () => {
      setLoading(true);
      try {
        const data = await LisService.getPatientRecords(doctorId, undefined, page, PAGE_SIZE);
        if (cancelled) return;
        setRecords(data.results ?? data);
        setTotalCount(data.count ?? (data.results ?? data).length);
      } catch (e) {
        if (cancelled) return;
        console.error("Failed to load records", e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchRecords();
    return () => { cancelled = true; };
  }, [doctorId, page, refreshKey]);

  // Re-fetch when the tab/window regains focus (catches new screenings)
  useEffect(() => {
    const handleFocus = () => setRefreshKey((k) => k + 1);
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, []);

  // Debounce the search input — the filter pass is O(n) over records,
  // so we wait 200ms of idle typing before re-running it. Prevents UI
  // stutter on large record sets.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchTerm), 200);
    return () => clearTimeout(t);
  }, [searchTerm]);

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

  const filteredRecords = React.useMemo(() => {
    const q = debouncedSearch.toLowerCase();
    if (!q) return records;
    return records.filter((r) =>
      String(r.name || "").toLowerCase().includes(q) ||
      String(r.patientId || "").toLowerCase().includes(q) ||
      String(r.labId || "").toLowerCase().includes(q)
    );
  }, [records, debouncedSearch]);

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
                            onClick={() => setDetailScreeningId(record.id)}
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
      <ScreeningDetailDrawer
        screeningId={detailScreeningId}
        onClose={() => setDetailScreeningId(null)}
        userRole={userRole}
        onReviewed={(updated) => {
          setRecords((prev) =>
            prev.map((r) => (r.id === updated.id ? { ...r, is_reviewed: true } : r))
          );
        }}
      />
    </div>
  );
};

export default PatientRecords;
