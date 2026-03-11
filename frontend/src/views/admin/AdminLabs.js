import React, { useState, useEffect } from "react";
import { Plus, Edit2, Power, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { AdminService } from "@/services/api";
import Modal from "@/components/common/Modal";
import ConfirmDialog from "@/components/common/ConfirmDialog";

const TIER_COLORS = {
  standard: "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300",
  enterprise: "bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400",
  pilot: "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400",
};

const INPUT_CLS = "block w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100";

const LabForm = ({ isEdit, form, setForm, formError, formLoading, onSubmit, onCancel }) => (
  <form onSubmit={onSubmit} className="space-y-4">
    {!isEdit && (
      <div>
        <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">Lab Code</label>
        <input required type="text" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} className={INPUT_CLS} placeholder="LAB-001" />
      </div>
    )}
    <div>
      <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">Lab Name</label>
      <input required type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={INPUT_CLS} placeholder="City General Hospital" />
    </div>
    <div>
      <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">Tier</label>
      <select value={form.tier} onChange={(e) => setForm({ ...form, tier: e.target.value })} className={INPUT_CLS}>
        <option value="standard">Standard</option>
        <option value="enterprise">Enterprise</option>
        <option value="pilot">Pilot</option>
      </select>
    </div>
    <div>
      <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">Contact Email</label>
      <input type="email" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} className={INPUT_CLS} placeholder="lab@hospital.com" />
    </div>
    {formError && (
      <p className="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30 px-3 py-2 rounded border border-red-200 dark:border-red-800">{formError}</p>
    )}
    <div className="flex gap-3">
      <button type="button" onClick={onCancel} className="flex-1 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800">Cancel</button>
      <button type="submit" disabled={formLoading} className="flex-1 py-2 bg-teal-700 text-white rounded-lg text-sm font-medium hover:bg-teal-800 disabled:opacity-50">
        {formLoading ? "Saving..." : isEdit ? "Save Changes" : "Create Lab"}
      </button>
    </div>
  </form>
);

const AdminLabs = () => {
  const [labs, setLabs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [editLab, setEditLab] = useState(null);
  const [formError, setFormError] = useState(null);
  const [formLoading, setFormLoading] = useState(false);
  const [confirmDeactivate, setConfirmDeactivate] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [actionError, setActionError] = useState(null);

  const emptyForm = { code: "", name: "", tier: "standard", contact_email: "" };
  const [form, setForm] = useState(emptyForm);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await AdminService.getLabs();
      setLabs(data);
    } catch (err) {
      setError(err?.response?.data?.error || "Failed to load labs.");
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
    setActionError(null);
    try {
      await AdminService.deactivateLab(lab.id);
      setConfirmDeactivate(null);
      load();
    } catch (err) {
      setConfirmDeactivate(null);
      setActionError(err?.response?.data?.error || "Failed to deactivate lab.");
    }
  };

  const handleReactivate = async (lab) => {
    setActionError(null);
    try {
      await AdminService.reactivateLab(lab.id);
      load();
    } catch (err) {
      setActionError(err?.response?.data?.error || "Failed to reactivate lab.");
    }
  };

  const handlePermanentDelete = async (lab) => {
    setActionError(null);
    try {
      await AdminService.permanentDeleteLab(lab.id);
      setConfirmDelete(null);
      load();
    } catch (err) {
      setConfirmDelete(null);
      setActionError(err?.response?.data?.error || "Failed to permanently remove lab.");
    }
  };

  const handleCancelForm = () => { setShowCreate(false); setEditLab(null); };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Labs</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Manage laboratories in your organisation.</p>
        </div>
        <button onClick={openCreate} className="flex items-center gap-2 px-4 py-2 bg-teal-700 text-white rounded-lg text-sm font-medium hover:bg-teal-800 transition-colors">
          <Plus className="h-4 w-4" /> Add Lab
        </button>
      </div>

      {actionError && (
        <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg px-4 py-3 flex items-center justify-between">
          <span>{actionError}</span>
          <button onClick={() => setActionError(null)} className="text-red-400 hover:text-red-600 text-xs ml-4">Dismiss</button>
        </div>
      )}

      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-4 space-y-3">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="animate-pulse flex items-center gap-4 px-4 py-3">
                <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-20" />
                <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-36" />
                <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-20" />
                <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-32" />
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
        ) : labs.length === 0 ? (
          <div className="p-8 text-center text-slate-400 dark:text-slate-500 text-sm">No labs found.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
              <tr>
                <th className="text-left px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">Code</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">Name</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">Tier</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">Email</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
              {labs.map((lab) => (
                <tr key={lab.id} className="hover:bg-slate-50 dark:hover:bg-slate-800">
                  <td className="px-4 py-3 font-mono text-xs text-slate-700 dark:text-slate-300">{lab.code}</td>
                  <td className="px-4 py-3 font-medium text-slate-800 dark:text-slate-100">{lab.name}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold capitalize ${TIER_COLORS[lab.tier] || "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300"}`}>
                      {lab.tier}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-500 dark:text-slate-400">{lab.contact_email || "—"}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium ${lab.is_active ? "text-green-600" : "text-slate-400 dark:text-slate-500"}`}>
                      {lab.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1 justify-end">
                      <button onClick={() => openEdit(lab)} aria-label={`Edit ${lab.name}`} className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 dark:text-slate-500 hover:text-teal-600">
                        <Edit2 className="h-4 w-4" />
                      </button>
                      {lab.is_active ? (
                        <button onClick={() => setConfirmDeactivate(lab)} aria-label={`Deactivate ${lab.name}`} className="p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-900/30 text-slate-400 dark:text-slate-500 hover:text-red-500">
                          <Power className="h-4 w-4" />
                        </button>
                      ) : (
                        <>
                          <button onClick={() => handleReactivate(lab)} aria-label={`Reactivate ${lab.name}`} title="Reactivate" className="p-1.5 rounded hover:bg-green-50 dark:hover:bg-green-900/30 text-slate-400 dark:text-slate-500 hover:text-green-600 transition-colors">
                            <RotateCcw className="h-4 w-4" />
                          </button>
                          <button onClick={() => setConfirmDelete(lab)} aria-label={`Delete ${lab.name}`} title="Permanently remove" className="p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-900/30 text-slate-400 dark:text-slate-500 hover:text-red-500 transition-colors">
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
        <Modal title="Add Lab" onClose={() => setShowCreate(false)}>
          <LabForm isEdit={false} form={form} setForm={setForm} formError={formError} formLoading={formLoading} onSubmit={handleSubmit} onCancel={handleCancelForm} />
        </Modal>
      )}
      {editLab && (
        <Modal title="Edit Lab" onClose={() => setEditLab(null)}>
          <LabForm isEdit={true} form={form} setForm={setForm} formError={formError} formLoading={formLoading} onSubmit={handleSubmit} onCancel={handleCancelForm} />
        </Modal>
      )}
      {confirmDeactivate && (
        <ConfirmDialog
          title="Deactivate Lab"
          message={`Are you sure you want to deactivate "${confirmDeactivate.name}"? It can be reactivated later.`}
          confirmText="Deactivate"
          destructive
          onConfirm={() => handleDeactivate(confirmDeactivate)}
          onCancel={() => setConfirmDeactivate(null)}
        />
      )}
      {confirmDelete && (
        <ConfirmDialog
          title="Permanently Remove Lab"
          message={`Are you sure you want to permanently remove "${confirmDelete.name}" (${confirmDelete.code})? This action cannot be undone.`}
          confirmText="Remove Permanently"
          destructive
          onConfirm={() => handlePermanentDelete(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
};

export default AdminLabs;
