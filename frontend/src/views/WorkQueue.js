import React, { useState, useEffect, useCallback } from "react";
import { LisService, getAccessToken } from "../services/api";
import useWebSocket from "../hooks/useWebSocket";
import {
  Activity,
  Clock,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  ChevronRight,
  User,
  Loader2,
} from "lucide-react";

const RISK_BADGE = {
  1: <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 border border-green-200 dark:border-green-800">Normal</span>,
  2: <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-800">Borderline</span>,
  3: <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300 border border-red-200 dark:border-red-800">Deficient</span>,
};

const TABS = [
  { key: "pending",     label: "Pending",     icon: Clock,         color: "amber" },
  { key: "in_progress", label: "In Progress", icon: Activity,      color: "blue"  },
  { key: "completed",   label: "Completed",   icon: CheckCircle2,  color: "green" },
];

const tabActive = {
  amber: "border-amber-500 text-amber-700 dark:text-amber-400",
  blue:  "border-blue-500  text-blue-700 dark:text-blue-400",
  green: "border-green-500 text-green-700 dark:text-green-400",
};
const tabBadge = {
  amber: "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400",
  blue:  "bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400",
  green: "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400",
};

const WorkQueue = () => {
  const [activeTab, setActiveTab]   = useState("pending");
  const [queueData, setQueueData]   = useState({ counts: {}, items: [] });
  const [loading, setLoading]       = useState(true);
  const [transitioning, setTransitioning] = useState(null); // screeningId being updated

  const load = useCallback(async (tab = activeTab) => {
    setLoading(true);
    try {
      const data = await LisService.getWorkQueue(tab);
      setQueueData(data);
    } catch (e) {
      console.error("WorkQueue load failed", e);
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => { load(activeTab); }, [activeTab, load]);

  // WebSocket: auto-refresh on status changes or new screenings
  const handleWsMessage = useCallback((msg) => {
    if (msg.type === "status_change" || msg.type === "new_screening") {
      load(activeTab);
    }
  }, [load, activeTab]);

  const { connected } = useWebSocket("/ws/queue/", handleWsMessage, {
    token: getAccessToken(),
  });

  const handleTabChange = (tab) => {
    setActiveTab(tab);
  };

  const handleTransition = async (screeningId, newStatus) => {
    setTransitioning(screeningId);
    try {
      await LisService.updateScreeningStatus(screeningId, newStatus);
      // Refresh current tab
      await load(activeTab);
    } catch (e) {
      console.error("Status transition failed", e);
    } finally {
      setTransitioning(null);
    }
  };

  const counts = queueData.counts || {};
  const items  = queueData.items  || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Work Queue</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">Triage and manage screening results</p>
        </div>
        <div className="flex items-center gap-3">
          {connected && (
            <span className="flex items-center gap-1.5 text-xs text-green-600">
              <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
              Live
            </span>
          )}
          <button
            onClick={() => load(activeTab)}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-2 text-sm text-slate-600 dark:text-slate-300 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
        <div className="flex border-b border-slate-200 dark:border-slate-700">
          {TABS.map(({ key, label, icon: Icon, color }) => {
            const isActive = activeTab === key;
            const count = counts[key] ?? 0;
            return (
              <button
                key={key}
                onClick={() => handleTabChange(key)}
                className={`flex-1 flex items-center justify-center gap-2 px-4 py-3.5 text-sm font-medium border-b-2 transition-colors ${
                  isActive
                    ? `${tabActive[color]} bg-slate-50 dark:bg-slate-800`
                    : "border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
                {count > 0 && (
                  <span className={`px-1.5 py-0.5 text-xs font-bold rounded-full ${isActive ? tabBadge[color] : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300"}`}>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Table */}
        {loading ? (
          <div className="py-16 flex flex-col items-center gap-3 text-slate-400 dark:text-slate-500">
            <Loader2 className="h-8 w-8 animate-spin" />
            <p className="text-sm">Loading queue...</p>
          </div>
        ) : items.length === 0 ? (
          <div className="py-16 flex flex-col items-center gap-3 text-slate-400 dark:text-slate-500">
            <CheckCircle2 className="h-10 w-10 text-slate-200 dark:text-slate-700" />
            <p className="text-sm font-medium">No {activeTab.replace("_", " ")} screenings</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-100 dark:divide-slate-700 text-sm">
              <thead className="bg-slate-50 dark:bg-slate-800">
                <tr>
                  <th className="px-5 py-3 text-left text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Patient</th>
                  <th className="px-5 py-3 text-left text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Lab / Performed By</th>
                  <th className="px-5 py-3 text-left text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Risk</th>
                  <th className="px-5 py-3 text-left text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Received</th>
                  <th className="px-5 py-3 text-right text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Action</th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-slate-900 divide-y divide-slate-100 dark:divide-slate-700">
                {items.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors">
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center">
                          <User className="h-4 w-4 text-slate-400 dark:text-slate-500" />
                        </div>
                        <div>
                          <p className="font-medium text-slate-800 dark:text-slate-100">{item.patientInitials || "—"}</p>
                          <p className="text-xs font-mono text-slate-400 dark:text-slate-500">{item.patientId}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <p className="font-mono text-slate-700 dark:text-slate-300">{item.labId || "—"}</p>
                      <p className="text-xs text-slate-400 dark:text-slate-500">{item.performedBy}</p>
                    </td>
                    <td className="px-5 py-4">
                      {RISK_BADGE[item.riskClass] ?? <span className="text-slate-400 dark:text-slate-500">—</span>}
                      {item.riskClass === 3 && (
                        <AlertTriangle className="inline h-3.5 w-3.5 text-red-500 ml-1" />
                      )}
                    </td>
                    <td className="px-5 py-4 text-slate-500 dark:text-slate-400 text-xs">
                      {new Date(item.createdAt).toLocaleString()}
                    </td>
                    <td className="px-5 py-4 text-right">
                      {activeTab === "pending" && (
                        <button
                          disabled={transitioning === item.id}
                          onClick={() => handleTransition(item.id, "in_progress")}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
                        >
                          {transitioning === item.id
                            ? <Loader2 className="h-3 w-3 animate-spin" />
                            : <ChevronRight className="h-3 w-3" />}
                          Start Review
                        </button>
                      )}
                      {activeTab === "in_progress" && (
                        <button
                          disabled={transitioning === item.id}
                          onClick={() => handleTransition(item.id, "completed")}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50"
                        >
                          {transitioning === item.id
                            ? <Loader2 className="h-3 w-3 animate-spin" />
                            : <CheckCircle2 className="h-3 w-3" />}
                          Complete
                        </button>
                      )}
                      {activeTab === "completed" && (
                        <span className="text-xs text-slate-400 dark:text-slate-500 italic">Done</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default WorkQueue;
