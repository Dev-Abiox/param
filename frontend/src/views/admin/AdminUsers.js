import React, { useState, useEffect } from "react";
import { UserPlus, Edit2, UserX, X, Check } from "lucide-react";
import { AdminService } from "@/services/api";

const ROLE_LABELS = { ADMIN: "Admin", LAB: "Lab Tech", DOCTOR: "Doctor" };
const ROLE_COLORS = {
  ADMIN: "bg-purple-100 text-purple-700",
  LAB: "bg-teal-100 text-teal-700",
  DOCTOR: "bg-blue-100 text-blue-700",
};

const Modal = ({ title, onClose, children }) => (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
    <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-slate-800">{title}</h3>
        <button onClick={onClose} className="p-1 rounded hover:bg-slate-100">
          <X className="h-5 w-5 text-slate-400" />
        </button>
      </div>
      {children}
    </div>
  </div>
);

const AdminUsers = () => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [createError, setCreateError] = useState(null);
  const [createLoading, setCreateLoading] = useState(false);

  const [form, setForm] = useState({ username: "", email: "", name: "", password: "", role: "LAB" });

  const load = async () => {
    setLoading(true);
    try {
      const data = await AdminService.getUsers();
      setUsers(data);
    } catch {
      // silent
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
      setForm({ username: "", email: "", name: "", password: "", role: "LAB" });
      load();
    } catch (err) {
      setCreateError(err?.response?.data?.error || "Failed to create user.");
    } finally {
      setCreateLoading(false);
    }
  };

  const handleDeactivate = async (userId) => {
    if (!window.confirm("Deactivate this user? They will no longer be able to sign in.")) return;
    try {
      await AdminService.deactivateUser(userId);
      load();
    } catch {
      // silent
    }
  };

  const inputCls = "block w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white text-slate-900";

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Users</h1>
          <p className="text-sm text-slate-500 mt-1">Manage users in your organisation.</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-teal-700 text-white rounded-lg text-sm font-medium hover:bg-teal-800 transition-colors"
        >
          <UserPlus className="h-4 w-4" /> Add User
        </button>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-slate-400 text-sm">Loading...</div>
        ) : users.length === 0 ? (
          <div className="p-8 text-center text-slate-400 text-sm">No users found.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Name</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Username</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Email</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Role</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium text-slate-800">{u.name || "—"}</td>
                  <td className="px-4 py-3 text-slate-600 font-mono text-xs">{u.username}</td>
                  <td className="px-4 py-3 text-slate-600">{u.email || "—"}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${ROLE_COLORS[u.role] || "bg-slate-100 text-slate-600"}`}>
                      {ROLE_LABELS[u.role] || u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {u.is_active ? (
                      <span className="flex items-center gap-1 text-xs text-green-600 font-medium">
                        <Check className="h-3 w-3" /> Active
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400 font-medium">Inactive</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {u.is_active && (
                      <button
                        onClick={() => handleDeactivate(u.id)}
                        className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-500 transition-colors"
                        title="Deactivate"
                      >
                        <UserX className="h-4 w-4" />
                      </button>
                    )}
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
                <label className="block text-xs font-medium text-slate-700 mb-1">Full Name</label>
                <input required type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={inputCls} placeholder="Jane Doe" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Username</label>
                <input required type="text" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} className={inputCls} placeholder="jane.doe" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Email</label>
                <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className={inputCls} placeholder="jane@hospital.com" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Password</label>
                <input required type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className={inputCls} placeholder="Min 8 chars" />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Role</label>
              <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} className={inputCls}>
                <option value="LAB">Lab Technician</option>
                <option value="DOCTOR">Doctor</option>
                <option value="ADMIN">Admin</option>
              </select>
            </div>
            {createError && (
              <p className="text-xs text-red-600 bg-red-50 px-3 py-2 rounded border border-red-200">{createError}</p>
            )}
            <div className="flex gap-3 pt-1">
              <button type="button" onClick={() => setShowCreate(false)} className="flex-1 py-2 border border-slate-300 rounded-lg text-sm text-slate-600 hover:bg-slate-50">
                Cancel
              </button>
              <button type="submit" disabled={createLoading} className="flex-1 py-2 bg-teal-700 text-white rounded-lg text-sm font-medium hover:bg-teal-800 disabled:opacity-50">
                {createLoading ? "Creating..." : "Create User"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
};

export default AdminUsers;
