import React, { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid } from "recharts";
import { Users, AlertTriangle, TrendingUp, Search, Download, Brain, Activity, Database, Server } from "lucide-react";
import { LisService } from "../services/api";

const AdminDashboard = () => {
  const [stats, setStats] = useState(null);
  const [latencyMs, setLatencyMs] = useState(null);
  const [loadError, setLoadError] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");

  const fetchStats = () => {
    setLoadError(false);
    setStats(null);
    const t0 = performance.now();
    LisService.getStats()
      .then((data) => {
        setLatencyMs(Math.round(performance.now() - t0));
        setStats(data);
      })
      .catch(() => setLoadError(true));
  };

  useEffect(() => { fetchStats(); }, []);

  const handleExportCSV = () => {
    if (!stats || !stats.recentCases) return;

    const headers = ["Case ID", "Date", "Patient Ref", "MCV (fL)", "Screening Result"];
    const rows = stats.recentCases.map((c) => [c.id, c.date, c.patientRef, c.mcv, c.result]);

    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `clinomic_labs_export_${new Date().toISOString().split("T")[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (loadError) {
    return (
      <div className="flex flex-col items-center justify-center h-96 text-slate-400 dark:text-slate-500" data-testid="admin-dashboard-error">
        <AlertTriangle className="w-8 h-8 mb-4 text-red-400" />
        <p className="mb-4">Failed to load analytics data.</p>
        <button onClick={fetchStats} className="px-4 py-2 bg-teal-600 text-white rounded hover:bg-teal-700 text-sm">
          Retry
        </button>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="flex flex-col items-center justify-center h-96 text-slate-400 dark:text-slate-500" data-testid="admin-dashboard-loading">
        <Activity className="w-8 h-8 animate-spin mb-4 text-teal-600" />
        <p>Loading analytics data...</p>
      </div>
    );
  }

  const filteredCases = (stats.recentCases || []).filter(
    (c) => String(c.id).toLowerCase().includes(searchTerm.toLowerCase()) || String(c.patientRef).toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6" data-testid="admin-dashboard">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Administrator Dashboard</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">System Status, ML Performance & Case Management</p>
        </div>
        <div className="flex items-center space-x-3">
          <div className="flex items-center px-4 py-2 bg-slate-800 text-teal-400 rounded-md shadow-sm border border-slate-700" data-testid="backend-status-card">
            <Server className="w-4 h-4 mr-2" />
            <div className="text-xs text-left">
              <div className="font-bold text-white">Backend Status</div>
              <div className="text-teal-400">Online • {stats.modelMetrics?.version}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-slate-900 p-5 rounded-sm border border-slate-200 dark:border-slate-700 shadow-sm flex items-center justify-between" data-testid="stat-total-screenings">
          <div>
            <p className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wide">Total User Screenings</p>
            <h3 className="text-3xl font-extrabold text-slate-800 dark:text-slate-100 mt-1">{Number(stats.totalCases || 0).toLocaleString()}</h3>
            <p className="text-xs text-green-600 font-medium mt-1 flex items-center">
              <TrendingUp className="w-3 h-3 mr-1" /> +{stats.dailyTests || 0} in last 24h
            </p>
          </div>
          <div className="p-3 rounded-full bg-teal-50 dark:bg-teal-900/30 text-teal-600 border border-teal-100 dark:border-teal-800">
            <Users className="w-6 h-6" />
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 p-5 rounded-sm border border-slate-200 dark:border-slate-700 shadow-sm flex items-center justify-between" data-testid="stat-model-accuracy">
          <div>
            <p className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wide">Model Accuracy</p>
            <h3 className="text-3xl font-extrabold text-slate-800 dark:text-slate-100 mt-1">{stats.modelMetrics?.accuracy}%</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{stats.modelMetrics?.validationDataset || "Validation set"}</p>
          </div>
          <div className="p-3 rounded-full bg-violet-50 dark:bg-violet-900/30 text-violet-600 border border-violet-100 dark:border-violet-800">
            <Brain className="w-6 h-6" />
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 p-5 rounded-sm border border-slate-200 dark:border-slate-700 shadow-sm flex items-center justify-between" data-testid="stat-high-risk">
          <div>
            <p className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wide">High Risk Detected</p>
            <h3 className="text-3xl font-extrabold text-slate-800 dark:text-slate-100 mt-1">{stats.distribution?.[2]?.value || 0}</h3>
            <p className="text-xs text-red-500 font-medium mt-1">{stats.totalCases ? (((stats.distribution?.[2]?.value || 0) / stats.totalCases) * 100).toFixed(1) : "0.0"}% of total cases</p>
          </div>
          <div className="p-3 rounded-full bg-red-50 dark:bg-red-900/30 text-red-600 border border-red-100 dark:border-red-800">
            <AlertTriangle className="w-6 h-6" />
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 p-5 rounded-sm border border-slate-200 dark:border-slate-700 shadow-sm flex items-center justify-between" data-testid="stat-latency">
          <div>
            <p className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wide">Backend API Latency</p>
            <h3 className="text-3xl font-extrabold text-slate-800 dark:text-slate-100 mt-1">{latencyMs !== null ? `${latencyMs}ms` : "—"}</h3>
            <p className={`text-xs font-medium mt-1 ${latencyMs !== null && latencyMs < 200 ? "text-green-600" : "text-amber-600"}`}>
              {latencyMs !== null ? (latencyMs < 200 ? "Optimal Performance" : "Elevated Latency") : "Measuring…"}
            </p>
          </div>
          <div className="p-3 rounded-full bg-blue-50 dark:bg-blue-900/30 text-blue-600 border border-blue-100 dark:border-blue-800">
            <Activity className="w-6 h-6" />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="bg-white dark:bg-slate-900 rounded-sm border border-slate-200 dark:border-slate-700 shadow-sm flex flex-col" data-testid="ml-metrics-panel">
          <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-700">
            <h4 className="font-bold text-slate-700 dark:text-slate-300 flex items-center">
              <Brain className="w-4 h-4 mr-2 text-violet-500" />
              Backend ML Metrics
            </h4>
          </div>
          <div className="p-6 flex-1 flex flex-col justify-center space-y-6">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-500 dark:text-slate-400">Recall (Sensitivity)</span>
                <span className="font-bold text-slate-800 dark:text-slate-100">{stats.modelMetrics?.recall}%</span>
              </div>
              <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-2">
                <div className="bg-violet-500 h-2 rounded-full" style={{ width: `${stats.modelMetrics?.recall || 0}%` }} />
              </div>
              <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1">Crucial for minimizing false negatives in screening.</p>
            </div>

            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-500 dark:text-slate-400">Precision</span>
                <span className="font-bold text-slate-800 dark:text-slate-100">{stats.modelMetrics?.precision}%</span>
              </div>
              <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-2">
                <div className="bg-violet-400 h-2 rounded-full" style={{ width: `${stats.modelMetrics?.precision || 0}%` }} />
              </div>
            </div>

            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-500 dark:text-slate-400">F1 Score</span>
                <span className="font-bold text-slate-800 dark:text-slate-100">{stats.modelMetrics?.f1Score}%</span>
              </div>
              <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-2">
                <div className="bg-violet-300 h-2 rounded-full" style={{ width: `${stats.modelMetrics?.f1Score || 0}%` }} />
              </div>
            </div>

            <div className="pt-4 border-t border-slate-100 dark:border-slate-700 grid grid-cols-2 gap-4 text-center">
              <div>
                <p className="text-xs text-slate-400 dark:text-slate-500">AUC - ROC</p>
                <p className="text-xl font-bold text-slate-800 dark:text-slate-100">{stats.modelMetrics?.auc}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 dark:text-slate-500">Training Loss</p>
                <p className="text-xl font-bold text-slate-800 dark:text-slate-100">{stats.modelMetrics?.trainingLoss ?? "—"}</p>
              </div>
            </div>
          </div>
        </div>

        <div className="lg:col-span-2 bg-white dark:bg-slate-900 p-6 rounded-sm border border-slate-200 dark:border-slate-700 shadow-sm" data-testid="distribution-chart">
          <h4 className="text-sm font-bold text-slate-700 dark:text-slate-300 mb-6">Screening Outcome Distribution</h4>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats.distribution || []} barSize={60}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#64748b" }} />
                <YAxis axisLine={false} tickLine={false} tick={{ fill: "#64748b" }} />
                <Tooltip cursor={{ fill: "#f8fafc" }} contentStyle={{ borderRadius: "4px", border: "none", boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)" }} />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {(stats.distribution || []).map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-sm shadow-sm overflow-hidden" data-testid="case-database-table">
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700 flex flex-col sm:flex-row justify-between items-center gap-4">
          <div className="flex items-center">
            <Database className="w-5 h-5 text-teal-600 mr-2" />
            <h4 className="font-bold text-slate-700 dark:text-slate-300">Case Database</h4>
          </div>

          <div className="flex items-center gap-3 w-full sm:w-auto">
            <div className="relative flex-1 sm:flex-none">
              <Search className="w-4 h-4 absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400 dark:text-slate-500" />
              <input
                data-testid="case-search-input"
                type="text"
                placeholder="Search ID or Patient..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-9 pr-3 py-1.5 text-sm border border-slate-300 dark:border-slate-600 rounded focus:outline-none focus:ring-1 focus:ring-teal-500 w-full bg-white dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <button data-testid="export-csv-button" onClick={handleExportCSV} className="flex items-center px-4 py-1.5 bg-slate-800 text-white text-sm font-medium rounded hover:bg-slate-700 transition-colors shadow-sm whitespace-nowrap">
              <Download className="w-4 h-4 mr-2" /> Export CSV
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-700 text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800">
              <tr>
                <th className="px-6 py-3 text-left font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider text-xs">Case ID</th>
                <th className="px-6 py-3 text-left font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider text-xs">Date</th>
                <th className="px-6 py-3 text-left font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider text-xs">Patient Ref</th>
                <th className="px-6 py-3 text-left font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider text-xs">MCV (fL)</th>
                <th className="px-6 py-3 text-center font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider text-xs">Result</th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-slate-900 divide-y divide-slate-100 dark:divide-slate-700">
              {filteredCases.slice(0, 10).map((item) => (
                <tr key={item.id} className="hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors">
                  <td className="px-6 py-3 font-mono text-xs text-slate-600 dark:text-slate-300">{item.id}</td>
                  <td className="px-6 py-3 text-slate-600 dark:text-slate-300">{item.date}</td>
                  <td className="px-6 py-3 font-medium text-slate-800 dark:text-slate-100">{item.patientRef}</td>
                  <td className="px-6 py-3 text-slate-600 dark:text-slate-300 font-mono">{item.mcv}</td>
                  <td className="px-6 py-3 text-center">
                    <span
                      className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
                        item.result === "High Risk"
                          ? "bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300 border border-red-200 dark:border-red-800"
                          : item.result === "Borderline"
                            ? "bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-800"
                            : "bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 border border-green-200 dark:border-green-800"
                      }`}
                    >
                      {item.result}
                    </span>
                  </td>
                </tr>
              ))}
              {filteredCases.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-slate-400 dark:text-slate-500">
                    No cases found matching your search.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="px-6 py-3 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-xs text-slate-500 dark:text-slate-400 flex justify-between items-center">
          <span>Showing recent 10 of {(stats.recentCases || []).length} entries</span>
          <span>Data synced: Just now</span>
        </div>
      </div>
    </div>
  );
};

export default AdminDashboard;
