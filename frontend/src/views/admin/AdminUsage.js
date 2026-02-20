import React, { useState, useEffect } from "react";
import { BarChart2, Calendar, TrendingUp } from "lucide-react";
import { BillingService } from "@/services/api";

const UsageBar = ({ pct }) => {
  const color = pct >= 90 ? "bg-red-500" : pct >= 70 ? "bg-amber-500" : "bg-teal-500";
  return (
    <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-3 overflow-hidden">
      <div className={`${color} h-3 rounded-full transition-all`} style={{ width: `${Math.min(pct, 100)}%` }} />
    </div>
  );
};

const AdminUsage = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await BillingService.getUsage();
        setData(res);
      } catch (err) {
        setError("Failed to load usage data.");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  if (loading) {
    return <div className="max-w-4xl mx-auto p-8 text-center text-slate-400 dark:text-slate-500">Loading...</div>;
  }

  if (error) {
    return <div className="max-w-4xl mx-auto p-8 text-center text-red-500">{error}</div>;
  }

  const limit = data?.monthly_limit === -1 ? null : data?.monthly_limit;
  const count = data?.current_count ?? 0;
  const pct = limit ? Math.round((count / limit) * 100) : 0;
  const history = data?.history ?? [];

  const maxHistory = Math.max(...history.map((h) => h.screening_count || 0), 1);

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Usage</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Monthly screening quota and historical usage.</p>
      </div>

      {/* Current Period Card */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 bg-teal-50 dark:bg-teal-900/30 rounded-lg flex items-center justify-center">
              <TrendingUp className="h-5 w-5 text-teal-600 dark:text-teal-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-300">Current Period</p>
              <p className="text-xs text-slate-400 dark:text-slate-500">
                Resets{" "}
                {data?.period_end
                  ? new Date(data.period_end).toLocaleDateString(undefined, { month: "long", day: "numeric" })
                  : "—"}
              </p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-3xl font-bold text-slate-900 dark:text-slate-100">{count.toLocaleString()}</p>
            <p className="text-sm text-slate-400 dark:text-slate-500">
              {limit ? `of ${limit.toLocaleString()} screenings` : "screenings (unlimited)"}
            </p>
          </div>
        </div>

        {limit && (
          <>
            <UsageBar pct={pct} />
            <div className="flex justify-between mt-2 text-xs text-slate-400 dark:text-slate-500">
              <span>{pct}% used</span>
              <span>{(limit - count).toLocaleString()} remaining</span>
            </div>
          </>
        )}

        <div className="mt-4 grid grid-cols-3 gap-4 border-t border-slate-100 dark:border-slate-700 pt-4">
          <div className="text-center">
            <p className="text-xs text-slate-400 dark:text-slate-500 mb-1">Plan</p>
            <p className="font-semibold text-slate-700 dark:text-slate-300 capitalize">{data?.plan || "—"}</p>
          </div>
          <div className="text-center">
            <p className="text-xs text-slate-400 dark:text-slate-500 mb-1">Monthly Limit</p>
            <p className="font-semibold text-slate-700 dark:text-slate-300">{limit ? limit.toLocaleString() : "Unlimited"}</p>
          </div>
          <div className="text-center">
            <p className="text-xs text-slate-400 dark:text-slate-500 mb-1">This Month</p>
            <p className="font-semibold text-slate-700 dark:text-slate-300">{count.toLocaleString()}</p>
          </div>
        </div>
      </div>

      {/* History Chart */}
      {history.length > 0 && (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm p-6">
          <div className="flex items-center gap-2 mb-6">
            <BarChart2 className="h-5 w-5 text-slate-400 dark:text-slate-500" />
            <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">Last 6 Months</h2>
          </div>
          <div className="flex items-end gap-3 h-32">
            {history.map((h, i) => {
              const barPct = (h.screening_count / maxHistory) * 100;
              return (
                <div key={i} className="flex-1 flex flex-col items-center gap-1">
                  <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">{h.screening_count}</p>
                  <div className="w-full flex items-end" style={{ height: "80px" }}>
                    <div
                      className="w-full bg-teal-500 rounded-t"
                      style={{ height: `${Math.max(barPct, 4)}%` }}
                    />
                  </div>
                  <p className="text-xs text-slate-400 dark:text-slate-500 text-center leading-tight">
                    {h.period_start
                      ? new Date(h.period_start).toLocaleDateString(undefined, { month: "short" })
                      : `M${i + 1}`}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminUsage;
