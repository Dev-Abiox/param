import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, RefreshCw, UserPlus, Trash2, Mail } from "lucide-react";
import { PlatformService } from "@/services/PlatformService";

const PLANS = ["starter", "professional", "enterprise"];

const STATUS_COLORS = {
  ACTIVE:    "bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-400",
  TRIAL:     "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400",
  SUSPENDED: "bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400",
  CANCELLED: "bg-slate-100 dark:bg-slate-700 text-slate-500",
  EXPIRED:   "bg-slate-100 dark:bg-slate-700 text-slate-500",
  PAST_DUE:  "bg-orange-100 dark:bg-orange-900/30 text-orange-700",
};

const UsageBar = ({ count, limit, pct }) => {
  const color = pct >= 90 ? "bg-red-500" : pct >= 70 ? "bg-amber-500" : "bg-teal-500";
  return (
    <div>
      <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400 mb-1">
        <span>{count.toLocaleString()} used</span>
        <span>{limit > 0 ? `${limit.toLocaleString()} limit` : "Unlimited"}</span>
      </div>
      <div className="h-2.5 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <p className={`text-right text-xs mt-0.5 font-medium ${
        pct >= 90 ? "text-red-600" : pct >= 70 ? "text-amber-600" : "text-slate-500 dark:text-slate-400"
      }`}>{pct}% used</p>
    </div>
  );
};

const ROLE_COLORS = {
  LAB:    "bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-400",
  DOCTOR: "bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400",
};

import { extractApiError as extractError } from "@/lib/utils";

const PlatformOrgDetail = () => {
  const { schema } = useParams();
  const navigate = useNavigate();
  const [org, setOrg] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("overview");

  // Plan change state
  const [selectedPlan, setSelectedPlan] = useState("");
  const [planLoading, setPlanLoading] = useState(false);
  const [planMsg, setPlanMsg] = useState(null);

  // Action state (suspend/reactivate/delete)
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);

  // Add user state
  const [showAddUser, setShowAddUser] = useState(false);
  const [userForm, setUserForm] = useState({ email: "", name: "", role: "LAB" });
  const [userLoading, setUserLoading] = useState(false);
  const [userMsg, setUserMsg] = useState(null);

  // Resend credentials state
  const [resendingId, setResendingId] = useState(null);

  const handleResendCredentials = async (userId, email) => {
    setResendingId(userId);
    setUserMsg(null);
    try {
      await PlatformService.resendCredentials(schema, userId);
      setUserMsg({ type: "success", text: `Credentials email sent to ${email}.` });
    } catch (err) {
      setUserMsg({ type: "error", text: extractError(err, "Failed to send credentials email.") });
    } finally {
      setResendingId(null);
    }
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await PlatformService.getOrg(schema);
      setOrg(data);
      setSelectedPlan(data.subscription?.plan?.name?.replace("_", "") || "");
    } catch (err) {
      console.error('[PlatformOrgDetail] load error:', err?.response?.status, err?.response?.data, err);
      setError(extractError(err, "Failed to load organisation."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [schema]);

  const handleAction = async (action) => {
    setActionLoading(true);
    setActionError(null);
    try {
      const updated = await PlatformService.updateOrg(schema, { action });
      setOrg((o) => ({ ...o, is_active: updated.is_active, subscription: { ...o.subscription, status: updated.status } }));
    } catch (err) {
      setActionError(extractError(err, `Failed to ${action} organisation.`));
    } finally {
      setActionLoading(false);
    }
  };

  const handlePlanChange = async () => {
    if (!selectedPlan) return;
    setPlanLoading(true);
    setPlanMsg(null);
    try {
      const res = await PlatformService.changeOrgPlan(schema, selectedPlan);
      setPlanMsg({ type: "success", text: `Plan changed to ${res.plan}` });
      load();
    } catch (err) {
      setPlanMsg({ type: "error", text: extractError(err, "Failed to change plan.") });
    } finally {
      setPlanLoading(false);
    }
  };

  const handleAddUser = async (e) => {
    e.preventDefault();
    setUserLoading(true);
    setUserMsg(null);
    try {
      await PlatformService.createOrgUser(schema, userForm);
      setUserMsg({ type: "success", text: "User created successfully." });
      setUserForm({ email: "", name: "", role: "LAB" });
      setShowAddUser(false);
      load();
    } catch (err) {
      setUserMsg({ type: "error", text: extractError(err, "Failed to create user.") });
    } finally {
      setUserLoading(false);
    }
  };

  const handleDelete = async () => {
    setDeleteLoading(true);
    try {
      await PlatformService.deleteOrg(schema);
      navigate("/platform-admin/orgs");
    } catch (err) {
      setActionError(extractError(err, "Failed to delete organisation."));
    } finally {
      setDeleteLoading(false);
      setDeleteConfirm(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin h-8 w-8 border-4 border-teal-600 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (error || !org) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 rounded-lg p-4 text-sm">{error || "Organisation not found."}</div>
      </div>
    );
  }

  const sub = org.subscription || {};
  const isSuspended = sub.status === "SUSPENDED";

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button onClick={() => navigate("/platform-admin/orgs")}
          className="p-2 text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg">
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">{org.name}</h1>
            <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${STATUS_COLORS[sub.status] || ""}`}>
              {sub.status || "—"}
            </span>
          </div>
          <p className="text-xs font-mono text-slate-400 mt-0.5">schema: {org.schema_name}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={load}
            className="p-2 text-slate-500 border border-slate-200 dark:border-slate-700 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700">
            <RefreshCw className="h-4 w-4" />
          </button>
          {isSuspended ? (
            <button onClick={() => handleAction("reactivate")} disabled={actionLoading}
              className="px-4 py-2 bg-teal-600 text-white text-sm font-medium rounded-lg hover:bg-teal-700 disabled:opacity-60">
              Reactivate
            </button>
          ) : (
            <button onClick={() => handleAction("suspend")} disabled={actionLoading}
              className="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 disabled:opacity-60">
              Suspend
            </button>
          )}
          <button onClick={() => setDeleteConfirm(true)}
            className="p-2 text-red-500 border border-red-200 dark:border-red-800 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20"
            title="Delete organisation">
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-slate-200 dark:border-slate-700 flex gap-6">
        {["overview", "billing", "users"].map((tab) => (
          <button key={tab} onClick={() => setActiveTab(tab)}
            className={`pb-3 text-sm font-medium capitalize border-b-2 transition-colors ${
              activeTab === tab
                ? "border-teal-500 text-teal-600 dark:text-teal-400"
                : "border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
            }`}>
            {tab}
          </button>
        ))}
      </div>

      {actionError && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 rounded-lg p-3 text-sm flex items-center justify-between">
          <span>{actionError}</span>
          <button onClick={() => setActionError(null)} className="text-red-400 hover:text-red-600 text-xs font-medium ml-4">Dismiss</button>
        </div>
      )}

      {/* ── Overview Tab ─────────────────────────────────────────── */}
      {activeTab === "overview" && (
        <div className="space-y-4">
          <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5 grid grid-cols-2 gap-4 text-sm">
            <div><p className="text-slate-400 dark:text-slate-500 text-xs mb-0.5">Organisation ID</p><p className="font-mono text-slate-700 dark:text-slate-300 text-xs">{org.id}</p></div>
            <div><p className="text-slate-400 dark:text-slate-500 text-xs mb-0.5">Schema</p><p className="font-mono text-slate-700 dark:text-slate-300">{org.schema_name}</p></div>
            <div><p className="text-slate-400 dark:text-slate-500 text-xs mb-0.5">Domain</p><p className="text-slate-700 dark:text-slate-300">{org.domain || "—"}</p></div>
            <div><p className="text-slate-400 dark:text-slate-500 text-xs mb-0.5">Created</p><p className="text-slate-700 dark:text-slate-300">{org.created_at ? new Date(org.created_at).toLocaleDateString() : "—"}</p></div>
          </div>

          {/* Recent payment events */}
          {org.payment_events?.length > 0 && (
            <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5">
              <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3">Recent Payment Events</h3>
              <div className="space-y-2">
                {org.payment_events.map((ev) => (
                  <div key={ev.id} className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-400">
                    <span className="font-mono">{ev.event_type}</span>
                    <span>{ev.created_at ? new Date(ev.created_at).toLocaleDateString() : ""}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Billing Tab ───────────────────────────────────────────── */}
      {activeTab === "billing" && (
        <div className="space-y-4">
          {/* Current plan */}
          <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5">
            <p className="text-xs text-slate-400 dark:text-slate-500 mb-1">Current Plan</p>
            <p className="text-xl font-bold text-slate-800 dark:text-slate-100 capitalize">
              {sub.plan_display || sub.plan || "—"}
            </p>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {sub.monthly_limit > 0 ? `${sub.monthly_limit.toLocaleString()} screenings / month` : "Unlimited screenings"}
            </p>
          </div>

          {/* Usage this period */}
          <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5">
            <p className="text-xs text-slate-400 dark:text-slate-500 mb-3">Usage This Period</p>
            <UsageBar
              count={sub.current_count || 0}
              limit={sub.monthly_limit || -1}
              pct={sub.pct_used || 0}
            />
          </div>

          {/* Change plan override */}
          <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3">Override Plan</h3>
            <p className="text-xs text-slate-400 dark:text-slate-500 mb-3">
              Direct override — no Razorpay payment required.
            </p>
            <div className="flex gap-3">
              <select
                value={selectedPlan}
                onChange={(e) => setSelectedPlan(e.target.value)}
                className="flex-1 px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300"
              >
                <option value="">Select plan…</option>
                {PLANS.map((p) => (
                  <option key={p} value={p} className="capitalize">{p}</option>
                ))}
              </select>
              <button
                onClick={handlePlanChange}
                disabled={planLoading || !selectedPlan}
                className="px-4 py-2 bg-teal-600 text-white text-sm font-medium rounded-lg hover:bg-teal-700 disabled:opacity-60"
              >
                {planLoading ? "Saving…" : "Apply"}
              </button>
            </div>
            {planMsg && (
              <p className={`text-sm mt-2 ${planMsg.type === "success" ? "text-teal-600 dark:text-teal-400" : "text-red-600 dark:text-red-400"}`}>
                {planMsg.text}
              </p>
            )}
          </div>

          {/* Usage history */}
          {org.usage_history?.length > 0 && (
            <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5">
              <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3">Usage History</h3>
              <div className="space-y-2">
                {org.usage_history.map((rec) => (
                  <div key={rec.id || rec.period_start} className="flex justify-between text-sm">
                    <span className="text-slate-600 dark:text-slate-400">{rec.period_start}</span>
                    <span className="font-medium text-slate-700 dark:text-slate-300">{rec.screening_count?.toLocaleString()} screenings</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Delete Confirmation Modal ────────────────────────────── */}
      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6 max-w-md w-full mx-4 shadow-xl">
            <h3 className="text-lg font-bold text-red-600 dark:text-red-400 mb-2">Delete Organisation</h3>
            <p className="text-sm text-slate-600 dark:text-slate-400 mb-1">
              This will permanently delete <strong>{org.name}</strong> including:
            </p>
            <ul className="text-sm text-slate-500 dark:text-slate-400 list-disc list-inside mb-4 space-y-1">
              <li>All users in this organisation</li>
              <li>All screening data and patient records</li>
              <li>The database schema and subscription</li>
            </ul>
            <p className="text-sm font-semibold text-red-600 dark:text-red-400 mb-4">This action cannot be undone.</p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setDeleteConfirm(false)}
                className="px-4 py-2 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 text-sm rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700">
                Cancel
              </button>
              <button onClick={handleDelete} disabled={deleteLoading}
                className="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 disabled:opacity-60">
                {deleteLoading ? "Deleting..." : "Delete Permanently"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Users Tab ─────────────────────────────────────────────── */}
      {activeTab === "users" && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <button
              onClick={() => setShowAddUser(true)}
              className="flex items-center gap-2 px-4 py-2 bg-teal-600 text-white text-sm font-medium rounded-lg hover:bg-teal-700"
            >
              <UserPlus className="h-4 w-4" />
              Add User
            </button>
          </div>

          {userMsg && (
            <div className={`text-sm p-3 rounded-lg ${userMsg.type === "success" ? "bg-teal-50 dark:bg-teal-900/20 text-teal-700 dark:text-teal-400" : "bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400"}`}>
              {userMsg.text}
            </div>
          )}

          {/* Add user form */}
          {showAddUser && (
            <form onSubmit={handleAddUser} className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5 space-y-4">
              <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">New User</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">Email *</label>
                  <input type="email" required value={userForm.email}
                    onChange={(e) => setUserForm((f) => ({ ...f, email: e.target.value }))}
                    className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-teal-500" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">Full Name</label>
                  <input value={userForm.name}
                    onChange={(e) => setUserForm((f) => ({ ...f, name: e.target.value }))}
                    className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-teal-500" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">Role</label>
                <select value={userForm.role} onChange={(e) => setUserForm((f) => ({ ...f, role: e.target.value }))}
                  className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                  <option value="LAB">Lab Manager</option>
                  <option value="DOCTOR">Doctor</option>
                </select>
              </div>
              <div className="flex gap-3">
                <button type="submit" disabled={userLoading}
                  className="px-4 py-2 bg-teal-600 text-white text-sm font-medium rounded-lg hover:bg-teal-700 disabled:opacity-60">
                  {userLoading ? "Creating…" : "Create User"}
                </button>
                <button type="button" onClick={() => setShowAddUser(false)}
                  className="px-4 py-2 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 text-sm rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700">
                  Cancel
                </button>
              </div>
            </form>
          )}

          {/* Users table */}
          <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 dark:bg-slate-700/50 border-b border-slate-200 dark:border-slate-700">
                <tr>
                  <th className="px-4 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">Name</th>
                  <th className="px-4 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">Email</th>
                  <th className="px-4 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">Role</th>
                  <th className="px-4 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">Status</th>
                  <th className="px-4 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">Last Login</th>
                  <th className="px-4 py-3 text-right font-semibold text-slate-600 dark:text-slate-300">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                {(org.users || []).length === 0 ? (
                  <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-400 dark:text-slate-500">No users found.</td></tr>
                ) : (
                  (org.users || []).map((u) => (
                    <tr key={u.id} className="hover:bg-slate-50 dark:hover:bg-slate-700/30">
                      <td className="px-4 py-3 font-medium text-slate-800 dark:text-slate-100">{u.name || u.username}</td>
                      <td className="px-4 py-3 text-slate-500 dark:text-slate-400">{u.email || "—"}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${ROLE_COLORS[u.role] || ""}`}>
                          {u.role}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${u.is_active ? "bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-400" : "bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400"}`}>
                          {u.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-400 dark:text-slate-500 text-xs">
                        {u.last_login ? new Date(u.last_login).toLocaleDateString() : "Never"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {u.email && (
                          <button
                            onClick={() => handleResendCredentials(u.id, u.email)}
                            disabled={resendingId === u.id}
                            title="Send credentials email"
                            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-teal-600 dark:text-teal-400 border border-teal-200 dark:border-teal-800 rounded-lg hover:bg-teal-50 dark:hover:bg-teal-900/20 disabled:opacity-50"
                          >
                            <Mail className="h-3.5 w-3.5" />
                            {resendingId === u.id ? "Sending..." : "Send Credentials"}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default PlatformOrgDetail;
