import React, { useEffect, useState } from "react";
import { LisService } from "../services/api";
import { Role } from "../types";
import { X, Loader2, CheckCircle2, MessageSquare, Download } from "lucide-react";
import { generateReport, buildCbcRowsFromSnapshot, buildResultFromScreening } from "@/lib/generateReport";
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";

/**
 * Shared screening detail drawer. Fetches the full screening (+ trend) by id
 * and renders CBC indices, probabilities, rules, trend chart, review panel
 * and PDF download. Used by both PatientRecords and WorkQueue.
 *
 * Props:
 *   screeningId        — uuid of the screening to display (null hides the drawer)
 *   onClose            — called when the user closes the drawer
 *   userRole           — current user's role (gates the review CTA)
 *   reviewCtaLabel     — override the "Mark as Reviewed" button text
 *   onReviewed         — async callback fired after a successful review;
 *                        receives (updatedScreening, note). Parent may
 *                        perform follow-up actions (e.g. transition status).
 */
const ScreeningDetailDrawer = ({
  screeningId,
  onClose,
  userRole,
  reviewCtaLabel = "Mark as Reviewed",
  onReviewed,
}) => {
  const [detailRecord, setDetailRecord] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [trend, setTrend] = useState(null);
  const [trendLoading, setTrendLoading] = useState(false);
  const [reviewNote, setReviewNote] = useState("");
  const [reviewing, setReviewing] = useState(false);
  const [reviewError, setReviewError] = useState(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    if (!screeningId) {
      setDetailRecord(null);
      setTrend(null);
      setReviewNote("");
      setReviewError(null);
      return;
    }

    let cancelled = false;
    (async () => {
      setDetailLoading(true);
      setDetailRecord(null);
      setTrend(null);
      setReviewNote("");
      setReviewError(null);
      try {
        const full = await LisService.getScreening(screeningId);
        if (cancelled) return;
        setDetailRecord(full);
        if (full.patient_id) {
          setTrendLoading(true);
          try {
            const td = await LisService.getPatientTrend(full.patient_id);
            if (!cancelled) setTrend(td.trend || []);
          } catch {
            if (!cancelled) setTrend([]);
          } finally {
            if (!cancelled) setTrendLoading(false);
          }
        }
      } catch (e) {
        console.error("Failed to load screening detail", e);
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [screeningId]);

  const handleMarkReviewed = async () => {
    if (!detailRecord) return;
    setReviewing(true);
    setReviewError(null);
    try {
      const result = await LisService.reviewScreening(detailRecord.id, reviewNote);
      const updated = { ...detailRecord, ...result };
      setDetailRecord(updated);
      if (onReviewed) {
        await onReviewed(updated, reviewNote);
      }
    } catch (e) {
      console.error("Review failed", e);
      setReviewError(e?.response?.data?.error || "Failed to submit review. Please try again.");
    } finally {
      setReviewing(false);
    }
  };

  const handleDownload = async () => {
    if (!detailRecord) return;
    setDownloading(true);
    try {
      const patient = {
        name: detailRecord.patient_name || "",
        id: detailRecord.patient_id || "",
        age: detailRecord.cbc_snapshot?.Age,
        sex: detailRecord.cbc_snapshot?.Sex,
        date: detailRecord.created_at ? new Date(detailRecord.created_at).toLocaleDateString() : "",
        labId: detailRecord.lab_name || "",
      };
      const result = buildResultFromScreening(detailRecord);
      const cbcRows = buildCbcRowsFromSnapshot(detailRecord.cbc_snapshot || {});
      const doc = await generateReport(patient, result, cbcRows);
      doc.save(`ClinomicLabs_Report_${patient.id}.pdf`);
    } catch (e) {
      console.error("Failed to generate report", e);
    } finally {
      setDownloading(false);
    }
  };

  if (!screeningId) return null;

  const canReview = userRole === Role.DOCTOR || userRole === Role.LAB;

  return (
    <div className="fixed inset-0 z-40 flex justify-end" aria-modal="true">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative z-50 w-full max-w-lg bg-white dark:bg-slate-900 shadow-xl overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800">
          <h3 className="text-base font-bold text-slate-800 dark:text-slate-100">Screening Details</h3>
          <button
            onClick={onClose}
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

            {detailRecord.rules_fired?.length > 0 && (
              <section>
                <p className="text-xs font-bold uppercase text-slate-400 dark:text-slate-500 mb-2">Clinical Interpretation</p>
                <ul className="list-disc list-inside space-y-1 text-slate-700 dark:text-slate-300">
                  {detailRecord.rules_fired.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              </section>
            )}

            <section>
              <p className="text-xs font-bold uppercase text-slate-400 dark:text-slate-500 mb-2">Patient CBC Trend</p>
              {trendLoading ? (
                <div className="flex items-center justify-center h-32">
                  <Loader2 className="w-5 h-5 animate-spin text-teal-500" />
                </div>
              ) : !trend || trend.length < 2 ? (
                <p className="text-xs text-slate-400 dark:text-slate-500 italic px-1 py-2">
                  Not enough history to chart a trend — this is the patient's first screening or only one prior record exists.
                </p>
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
                canReview && (
                  <div className="space-y-2">
                    <textarea
                      rows={3}
                      placeholder="Optional clinical note..."
                      value={reviewNote}
                      onChange={(e) => setReviewNote(e.target.value)}
                      disabled={reviewing}
                      className="w-full text-xs border border-slate-300 dark:border-slate-600 rounded px-2.5 py-2 focus:outline-none focus:ring-1 focus:ring-teal-500 resize-none bg-white dark:bg-slate-800 disabled:opacity-50"
                    />
                    {reviewError && (
                      <p className="text-xs text-red-600 dark:text-red-400">{reviewError}</p>
                    )}
                    <button
                      onClick={handleMarkReviewed}
                      disabled={reviewing}
                      className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded text-sm font-medium disabled:opacity-50"
                    >
                      {reviewing
                        ? <Loader2 className="w-4 h-4 animate-spin" />
                        : <MessageSquare className="w-4 h-4" />}
                      {reviewCtaLabel}
                    </button>
                  </div>
                )
              )}
            </section>

            <button
              onClick={handleDownload}
              disabled={downloading}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-800 text-white rounded text-sm font-medium disabled:opacity-50"
            >
              {downloading
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <Download className="w-4 h-4" />}
              Download PDF Report
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default ScreeningDetailDrawer;
