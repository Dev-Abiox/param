import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Building2, CheckCircle, Clock, PauseCircle, TrendingUp, Plus, RefreshCw } from "lucide-react";
import { PlatformService } from "@/services/PlatformService";

const StatCard = ({ icon: Icon, label, value, color }) => (
  <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5 flex items-center gap-4">
    <div className={`p-3 rounded-lg ${color}`}>
      <Icon className="h-6 w-6" />
    </div>
    <div>
      <p className="text-sm text-slate-500 dark:text-slate-400">{label}</p>
      <p className="text-2xl font-bold text-slate-800 dark:text-slate-100">{value ?? "—"}</p>
    </div>
  </div>
);

const PlatformDashboard = () => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await PlatformService.getStats();
      setStats(data);
    } catch {
      setError("Failed to load platform stats.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const formatINR = (v) =>
    new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(v || 0);

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Platform Admin</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Cross-tenant SaaS management — all labs, billing, and users
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={load}
            className="flex items-center gap-2 px-3 py-2 text-sm text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
          <button
            onClick={() => navigate("/platform-admin/orgs/new")}
            className="flex items-center gap-2 px-4 py-2 bg-teal-600 text-white text-sm font-medium rounded-lg hover:bg-teal-700"
          >
            <Plus className="h-4 w-4" />
            Create Lab
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 rounded-lg p-4 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin h-8 w-8 border-4 border-teal-600 border-t-transparent rounded-full" />
        </div>
      ) : (
        <>
          {/* Stat cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard icon={Building2} label="Total Labs" value={stats?.total_orgs}
              color="bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400" />
            <StatCard icon={CheckCircle} label="Active" value={stats?.active_orgs}
              color="bg-teal-100 dark:bg-teal-900/30 text-teal-600 dark:text-teal-400" />
            <StatCard icon={Clock} label="Trial" value={stats?.trial_orgs}
              color="bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400" />
            <StatCard icon={PauseCircle} label="Suspended" value={stats?.suspended_orgs}
              color="bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400" />
          </div>

          {/* Revenue + screenings */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5">
              <p className="text-sm text-slate-500 dark:text-slate-400 mb-1">Monthly Recurring Revenue</p>
              <p className="text-3xl font-bold text-teal-600 dark:text-teal-400">
                {formatINR(stats?.mrr_inr)}
              </p>
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">Active subscriptions only</p>
            </div>
            <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5">
              <p className="text-sm text-slate-500 dark:text-slate-400 mb-1">Screenings This Month</p>
              <p className="text-3xl font-bold text-slate-800 dark:text-slate-100">
                {(stats?.total_screenings_this_month || 0).toLocaleString()}
              </p>
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">Across all labs</p>
            </div>
          </div>

          {/* Plan breakdown */}
          {stats?.plan_breakdown && (
            <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5">
              <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3">Plan Breakdown</h3>
              <div className="flex flex-wrap gap-3">
                {Object.entries(stats.plan_breakdown).map(([plan, count]) => (
                  <div key={plan} className="flex items-center gap-2 px-3 py-2 bg-slate-50 dark:bg-slate-700 rounded-lg">
                    <span className="text-sm font-medium text-slate-700 dark:text-slate-300 capitalize">{plan}</span>
                    <span className="text-xs font-bold text-white bg-teal-600 rounded-full px-2 py-0.5">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Quick link */}
          <div
            onClick={() => navigate("/platform-admin/orgs")}
            className="cursor-pointer bg-slate-50 dark:bg-slate-800 hover:bg-teal-50 dark:hover:bg-teal-900/20 border border-slate-200 dark:border-slate-700 rounded-xl p-4 flex items-center justify-between transition-colors"
          >
            <div className="flex items-center gap-3">
              <TrendingUp className="h-5 w-5 text-teal-600" />
              <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                View all {stats?.total_orgs} labs →
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default PlatformDashboard;
