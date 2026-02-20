import React, { useState, useEffect } from "react";
import { Plus, Edit2, Power, X } from "lucide-react";
import { AdminService } from "@/services/api";

const TIER_COLORS = {
  standard: "bg-slate-100 text-slate-600",
  enterprise: "bg-purple-100 text-purple-700",
  pilot: "bg-amber-100 text-amber-700",
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

const AdminLabs = () => {
  const [labs, setLabs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editLab, setEditLab] = useState(null);
  const [formError, setFormError] = useState(null);
  const [formLoading, setFormLoading] = useState(false);

  const emptyForm = { code: "", name: "", tier: "standard", contact_email: "" };
  const [form, setForm] = useState(emptyForm);

  const load = async () => {
    setLoading(true);
    try {
      const data = await AdminService.getLabs();
      setLabs(data);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const openCreate = () => { setForm(emptyForm); setFormError(null); setShowCreate(true); };
  const openEdit = (lab) => { setForm({ code: lab.code, name: lab.name, tier: lab.tier, contact_email: lab.contact_email }); setEditLab(lab); setFormError(null); };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormError(null);
    setFormLoading(true);
    try {
      if (editLab) {
        await AdminService.updateLab(editLab.id, { name: form.name, tier: form.tier, contact_email: form.contact_email });
        setEditLab(null);
      } else {
        await AdminService.createLab(form);
        setShowCreate(false);
      }
      load();
    } catch (err) {
      setFormError(err?.response?.data?.error || "Operation failed.");
    } finally {
      setFormLoading(false);
    }
  };

  const handleDeactivate = async (lab) => {
    if (!window.confirm(`Deactivate lab "${lab.name}"?`)) return;
    try {
      await AdminService.deactivateLab(lab.id);
      load();
    } catch {
      // silent
    }
  };

  const inputCls = "block w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white text-slate-900";

  const LabForm = ({ isEdit }) => (
    <form onSubmit={handleSubmit} className="space-y-4">
      {!isEdit && (
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">Lab Code</label>
          <input required type="text" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} className={inputCls} placeholder="LAB-001" />
        </div>
      )}
      <div>
        <label className="block text-xs font-medium text-slate-700 mb-1">Lab Name</label>
        <input required type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={inputCls} placeholder="City General Hospital" />
      </div>
      <div>
        <label className="block text-xs font-medium text-slate-700 mb-1">Tier</label>
        <select value={form.tier} onChange={(e) => setForm({ ...form, tier: e.target.value })} className={inputCls}>
          <option value="standard">Standard</option>
          <option value="enterprise">Enterprise</option>
          <option value="pilot">Pilot</option>
        </select>
      </div>
      <div>
        <label className="block text-xs font-medium text-slate-700 mb-1">Contact Email</label>
        <input type="email" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} className={inputCls} placeholder="lab@hospital.com" />
      </div>
      {formError && (
        <p className="text-xs text-red-600 bg-red-50 px-3 py-2 rounded border border-red-200">{formError}</p>
      )}
      <div className="flex gap-3">
        <button type="button" onClick={() => { setShowCreate(false); setEditLab(null); }} className="flex-1 py-2 border border-slate-300 rounded-lg text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
        <button type="submit" disabled={formLoading} className="flex-1 py-2 bg-teal-700 text-white rounded-lg text-sm font-medium hover:bg-teal-800 disabled:opacity-50">
          {formLoading ? "Saving..." : isEdit ? "Save Changes" : "Create Lab"}
        </button>
      </div>
    </form>
  );

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Labs</h1>
          <p className="text-sm text-slate-500 mt-1">Manage laboratories in your organisation.</p>
        </div>
        <button onClick={openCreate} className="flex items-center gap-2 px-4 py-2 bg-teal-700 text-white rounded-lg text-sm font-medium hover:bg-teal-800 transition-colors">
          <Plus className="h-4 w-4" /> Add Lab
        </button>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-slate-400 text-sm">Loading...</div>
        ) : labs.length === 0 ? (
          <div className="p-8 text-center text-slate-400 text-sm">No labs found.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Code</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Name</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Tier</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Email</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {labs.map((lab) => (
                <tr key={lab.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-mono text-xs text-slate-700">{lab.code}</td>
                  <td className="px-4 py-3 font-medium text-slate-800">{lab.name}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold capitalize ${TIER_COLORS[lab.tier] || "bg-slate-100 text-slate-600"}`}>
                      {lab.tier}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-500">{lab.contact_email || "—"}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium ${lab.is_active ? "text-green-600" : "text-slate-400"}`}>
                      {lab.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1 justify-end">
                      <button onClick={() => openEdit(lab)} className="p-1.5 rounded hover:bg-slate-100 text-slate-400 hover:text-teal-600">
                        <Edit2 className="h-4 w-4" />
                      </button>
                      {lab.is_active && (
                        <button onClick={() => handleDeactivate(lab)} className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-500">
                          <Power className="h-4 w-4" />
                        </button>
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
        <Modal title="Add Lab" onClose={() => setShowCreate(false)}>
          <LabForm isEdit={false} />
        </Modal>
      )}
      {editLab && (
        <Modal title="Edit Lab" onClose={() => setEditLab(null)}>
          <LabForm isEdit={true} />
        </Modal>
      )}
    </div>
  );
};

export default AdminLabs;
