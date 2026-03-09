import React, { useState, useEffect } from "react";
import { UserPlus, UserX, UserCheck, Trash2, Check, RefreshCw } from "lucide-react";
import { AdminService } from "@/services/api";
import Modal from "@/components/common/Modal";
import ConfirmDialog from "@/components/common/ConfirmDialog";

const ROLE_LABELS = { SUPER_ADMIN: "Platform Owner", LAB: "Lab Manager", DOCTOR: "Technician" };
const ROLE_COLORS = {
  SUPER_ADMIN: "bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400",
  LAB: "bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-400",
  DOCTOR: "bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400",
};

const AdminUsers = ({ user: currentUser }) => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [createError, setCreateError] = useState(null);
  const [createLoading, setCreateLoading] = useState(false);

  const [confirmDeactivate, setConfirmDeactivate] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);

  const [form, setForm] = useState({ username: "", email: "", name: "", password: "", role: "DOCTOR" });

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await AdminService.getUsers();
      setUsers(data);
    } catch (err) {
      setError(err?.response?.data?.error || "Failed to load users.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    setCreateError(null);
    setCreateLoading(true);
    try {
      await AdminService.createUser(form);
      setShowCreate(false);
      setForm({ username: "", email: "", name: "", password: "", role: currentUser?.role === "LAB" ? "DOCTOR" : "LAB" });
      load();
    } catch (err) {
      setCreateError(err?.response?.data?.error || "Failed to create user.");
    } finally {
      setCreateLoading(false);
    }
  };

  const handleDeactivate = async (user) => {
    try {
      await AdminService.deactivateUser(user.id);
      setConfirmDeactivate(null);
      load();
    } catch (err) {
      setError(err?.response?.data?.error || "Failed to deactivate user.");
      setConfirmDeactivate(null);
    }
  };

  const handleReactivate = async (user) => {
    try {
      await AdminService.reactivateUser(user.id);
      load();
    } catch (err) {
      setError(err?.response?.data?.error || "Failed to reactivate user.");
    }
  };

  const handlePermanentDelete = async (user) => {
    try {
      await AdminService.permanentDeleteUser(user.id);
      setConfirmDelete(null);
      load();
    } catch (err) {
      setError(err?.response?.data?.error || "Failed to delete user.");
      setConfirmDelete(null);
    }
  };

  const inputCls = "block w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100";

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Users</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Manage users in your organisation.</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-teal-700 text-white rounded-lg text-sm font-medium hover:bg-teal-800 transition-colors"
        >
          <UserPlus className="h-4 w-4" /> Add User
        </button>
      </div>

      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-4 space-y-3">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="animate-pulse flex items-center gap-4 px-4 py-3">
                <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-28" />
                <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-20" />
                <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-36" />
                <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-16" />
                <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-14" />
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="p-8 text-center">
            <p className="text-sm text-red-600 dark:text-red-400 mb-3">{error}</p>
            <button onClick={load} className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-teal-700 dark:text-teal-400 border border-teal-300 dark:border-teal-700 rounded-lg hover:bg-teal-50 dark:hover:bg-teal-900/30">
              <RefreshCw className="h-4 w-4" /> Retry
            </button>
          </div>
        ) : users.length === 0 ? (
          <div className="p-8 text-center text-slate-400 dark:text-slate-500 text-sm">No users found.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
              <tr>
                <th className="text-left px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">Name</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">Username</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">Email</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">Role</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-slate-50 dark:hover:bg-slate-800">
                  <td className="px-4 py-3 font-medium text-slate-800 dark:text-slate-100">{u.name || "—"}</td>
                  <td className="px-4 py-3 text-slate-600 dark:text-slate-300 font-mono text-xs">{u.username}</td>
                  <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{u.email || "—"}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${ROLE_COLORS[u.role] || "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300"}`}>
                      {ROLE_LABELS[u.role] || u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {u.is_active ? (
                      <span className="flex items-center gap-1 text-xs text-green-600 font-medium">
                        <Check className="h-3 w-3" /> Active
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400 dark:text-slate-500 font-medium">Inactive</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center gap-1 justify-end">
                      {u.is_active ? (
                        <button
                          onClick={() => setConfirmDeactivate(u)}
                          aria-label={`Deactivate ${u.name || u.username}`}
                          className="p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-900/30 text-slate-400 dark:text-slate-500 hover:text-red-500 transition-colors"
                        >
                          <UserX className="h-4 w-4" />
                        </button>
                      ) : (
                        <>
                          <button
                            onClick={() => handleReactivate(u)}
                            aria-label={`Reactivate ${u.name || u.username}`}
                            title="Reactivate"
                            className="p-1.5 rounded hover:bg-green-50 dark:hover:bg-green-900/30 text-slate-400 dark:text-slate-500 hover:text-green-600 transition-colors"
                          >
                            <UserCheck className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => setConfirmDelete(u)}
                            aria-label={`Delete ${u.name || u.username}`}
                            title="Permanently remove"
                            className="p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-900/30 text-slate-400 dark:text-slate-500 hover:text-red-500 transition-colors"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showCreate && (
        <Modal title="Add User" onClose={() => { setShowCreate(false); setCreateError(null); }}>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">Full Name</label>
                <input required type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={inputCls} placeholder="Jane Doe" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">Username</label>
                <input required type="text" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} className={inputCls} placeholder="jane.doe" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">Email</label>
                <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className={inputCls} placeholder="jane@hospital.com" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">Password</label>
                <input required type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className={inputCls} placeholder="Min 8 chars" />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">Role</label>
              <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} className={inputCls}>
                <option value="DOCTOR">Technician</option>
                <option value="LAB">Lab Manager</option>
              </select>
            </div>
            {createError && (
              <p className="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30 px-3 py-2 rounded border border-red-200 dark:border-red-800">{createError}</p>
            )}
            <div className="flex gap-3 pt-1">
              <button type="button" onClick={() => setShowCreate(false)} className="flex-1 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800">
                Cancel
              </button>
              <button type="submit" disabled={createLoading} className="flex-1 py-2 bg-teal-700 text-white rounded-lg text-sm font-medium hover:bg-teal-800 disabled:opacity-50">
                {createLoading ? "Creating..." : "Create User"}
              </button>
            </div>
          </form>
        </Modal>
      )}
      {confirmDeactivate && (
        <ConfirmDialog
          title="Deactivate User"
          message={`Are you sure you want to deactivate "${confirmDeactivate.name || confirmDeactivate.username}"? They will no longer be able to sign in.`}
          confirmText="Deactivate"
          destructive
          onConfirm={() => handleDeactivate(confirmDeactivate)}
          onCancel={() => setConfirmDeactivate(null)}
        />
      )}
      {confirmDelete && (
        <ConfirmDialog
          title="Permanently Remove User"
          message={`Are you sure you want to permanently remove "${confirmDelete.name || confirmDelete.username}"? This action cannot be undone.`}
          confirmText="Remove Permanently"
          destructive
          onConfirm={() => handlePermanentDelete(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
};

export default AdminUsers;
