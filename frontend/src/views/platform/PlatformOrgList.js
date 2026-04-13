import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Search, ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { PlatformService } from "@/services/PlatformService";

const STATUS_COLORS = {
  ACTIVE:    "bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-400",
  TRIAL:     "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400",
  SUSPENDED: "bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400",
  CANCELLED: "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-400",
  EXPIRED:   "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-400",
  PAST_DUE:  "bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400",
};

const UsageBar = ({ pct }) => {
  const color = pct >= 90 ? "bg-red-500" : pct >= 70 ? "bg-amber-500" : "bg-teal-500";
  return (
    <div className="w-24">
      <div className="h-1.5 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{pct}%</p>
    </div>
  );
};

const PlatformOrgList = () => {
  const [data, setData] = useState({ count: 0, results: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [planFilter, setPlanFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const navigate = useNavigate();
  const pageSize = 20;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await PlatformService.getOrgs({
        page,
        page_size: pageSize,
        search: search || undefined,
        plan: planFilter || undefined,
        status: statusFilter || undefined,
      });
      setData(result);
    } catch {
      setError("Failed to load organisations.");
    } finally {
      setLoading(false);
    }
  }, [page, search, planFilter, statusFilter]);

  useEffect(() => { load(); }, [load]);

  const totalPages = Math.ceil(data.count / pageSize);

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">All Labs</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">{data.count} organisations</p>
        </div>
        <div className="flex gap-3">
          <button onClick={load}
            className="flex items-center gap-2 px-3 py-2 text-sm text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700">
            <RefreshCw className="h-4 w-4" />
          </button>
          <button onClick={() => navigate("/platform-admin/orgs/new")}
            className="flex items-center gap-2 px-4 py-2 bg-teal-600 text-white text-sm font-medium rounded-lg hover:bg-teal-700">
            <Plus className="h-4 w-4" />
            Create Lab
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            placeholder="Search by name..."
            className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-teal-500"
          />
        </div>
        <select
          value={planFilter}
          onChange={(e) => { setPlanFilter(e.target.value); setPage(1); }}
          className="px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300"
        >
          <option value="">All Plans</option>
          <option value="starter">Starter</option>
          <option value="growth">Growth</option>
          <option value="chain">Chain</option>
          <option value="enterprise">Enterprise</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
          className="px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300"
        >
          <option value="">All Statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="TRIAL">Trial</option>
          <option value="SUSPENDED">Suspended</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 rounded-lg p-4 text-sm">{error}</div>
      )}

      {/* Table */}
      <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="animate-spin h-8 w-8 border-4 border-teal-600 border-t-transparent rounded-full" />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-700/50 border-b border-slate-200 dark:border-slate-700">
              <tr>
                <th className="px-4 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">Lab Name</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">Plan</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">Status</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">Usage</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">Admin</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">Created</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
              {data.results.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-slate-400 dark:text-slate-500">
                    No organisations found.
                  </td>
                </tr>
              ) : (
                data.results.map((org) => (
                  <tr key={org.id} className="hover:bg-slate-50 dark:hover:bg-slate-700/30">
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-800 dark:text-slate-100">{org.name}</p>
                      <p className="text-xs text-slate-400 font-mono">{org.schema_name}</p>
                    </td>
                    <td className="px-4 py-3 text-slate-600 dark:text-slate-300 capitalize">
                      {org.subscription?.plan_display || org.subscription?.plan || "—"}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[org.subscription?.status] || STATUS_COLORS.CANCELLED}`}>
                        {org.subscription?.status || "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {org.subscription?.monthly_limit > 0 ? (
                        <UsageBar pct={org.subscription.pct_used || 0} />
                      ) : (
                        <span className="text-xs text-slate-400">Unlimited</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-500 dark:text-slate-400 text-xs truncate max-w-32">
                      {org.admin_email || "—"}
                    </td>
                    <td className="px-4 py-3 text-slate-500 dark:text-slate-400 text-xs">
                      {org.created_at ? new Date(org.created_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => navigate(`/platform-admin/orgs/${org.schema_name}`)}
                        className="px-3 py-1 text-xs text-teal-600 dark:text-teal-400 border border-teal-200 dark:border-teal-800 rounded hover:bg-teal-50 dark:hover:bg-teal-900/20"
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Page {page} of {totalPages}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-2 text-slate-500 border border-slate-200 dark:border-slate-700 rounded-lg disabled:opacity-40 hover:bg-slate-50 dark:hover:bg-slate-700"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="p-2 text-slate-500 border border-slate-200 dark:border-slate-700 rounded-lg disabled:opacity-40 hover:bg-slate-50 dark:hover:bg-slate-700"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default PlatformOrgList;
