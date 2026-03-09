import React, { useState, useEffect } from "react";
import { Plus, Edit2, Power, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { AdminService } from "@/services/api";
import Modal from "@/components/common/Modal";
import ConfirmDialog from "@/components/common/ConfirmDialog";

const INPUT_CLS = "block w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100";

const DoctorForm = ({ isEdit, form, setForm, labs, formError, formLoading, onSubmit, onCancel }) => (
  <form onSubmit={onSubmit} className="space-y-4">
    {!isEdit && (
      <div>
        <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">Doctor Code</label>
        <input required type="text" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} className={INPUT_CLS} placeholder="D001" />
      </div>
    )}
    <div>
      <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">Full Name</label>
      <input required type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={INPUT_CLS} placeholder="Dr. Jane Smith" />
    </div>
    <div className="grid grid-cols-2 gap-3">
      <div>
        <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">Department</label>
        <input type="text" value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} className={INPUT_CLS} placeholder="Haematology" />
      </div>
      <div>
        <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">Specialization</label>
        <input type="text" value={form.specialization} onChange={(e) => setForm({ ...form, specialization: e.target.value })} className={INPUT_CLS} placeholder="B12 Disorders" />
      </div>
    </div>
    <div>
      <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">Email</label>
      <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className={INPUT_CLS} placeholder="doctor@hospital.com" />
    </div>
    <div>
      <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">Lab</label>
      <select required value={form.lab_id} onChange={(e) => setForm({ ...form, lab_id: e.target.value })} className={INPUT_CLS}>
        <option value="">Select a lab…</option>
        {labs.map((l) => <option key={l.id} value={l.id}>{l.name} ({l.code})</option>)}
      </select>
    </div>
    {formError && (
      <p className="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30 px-3 py-2 rounded border border-red-200 dark:border-red-800">{formError}</p>
    )}
    <div className="flex gap-3">
      <button type="button" onClick={onCancel} className="flex-1 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800">Cancel</button>
      <button type="submit" disabled={formLoading} className="flex-1 py-2 bg-teal-700 text-white rounded-lg text-sm font-medium hover:bg-teal-800 disabled:opacity-50">
        {formLoading ? "Saving..." : isEdit ? "Save Changes" : "Create Doctor"}
      </button>
    </div>
  </form>
);

const AdminDoctors = () => {
  const [doctors, setDoctors] = useState([]);
  const [labs, setLabs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [editDoctor, setEditDoctor] = useState(null);
  const [formError, setFormError] = useState(null);
  const [formLoading, setFormLoading] = useState(false);
  const [confirmDeactivate, setConfirmDeactivate] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);

  const emptyForm = { code: "", name: "", department: "", specialization: "", email: "", lab_id: "" };
  const [form, setForm] = useState(emptyForm);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [docData, labData] = await Promise.all([
        AdminService.getDoctors(),
        AdminService.getLabs(),
      ]);
      setDoctors(docData);
      setLabs(labData.filter((l) => l.is_active));
    } catch (err) {
      setError(err?.response?.data?.error || "Failed to load doctors.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const openCreate = () => { setForm(emptyForm); setFormError(null); setShowCreate(true); };
  const openEdit = (doc) => {
    setForm({ code: doc.code, name: doc.name, department: doc.department, specialization: doc.specialization, email: doc.email, lab_id: doc.lab_id });
    setEditDoctor(doc);
    setFormError(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormError(null);
    setFormLoading(true);
    try {
      if (editDoctor) {
        await AdminService.updateDoctor(editDoctor.id, {
          name: form.name, department: form.department, specialization: form.specialization, email: form.email, lab_id: form.lab_id,
        });
        setEditDoctor(null);
      } else {
        await AdminService.createDoctor(form);
        setShowCreate(false);
      }
      load();
    } catch (err) {
      setFormError(err?.response?.data?.error || "Operation failed.");
    } finally {
      setFormLoading(false);
    }
  };

  const handleDeactivate = async (doc) => {
    try {
      await AdminService.deactivateDoctor(doc.id);
      setConfirmDeactivate(null);
      load();
    } catch (err) {
      setError(err?.response?.data?.error || "Failed to deactivate doctor.");
      setConfirmDeactivate(null);
    }
  };

  const handleReactivate = async (doc) => {
    try {
      await AdminService.reactivateDoctor(doc.id);
      load();
    } catch (err) {
      setError(err?.response?.data?.error || "Failed to reactivate doctor.");
    }
  };

  const handlePermanentDelete = async (doc) => {
    try {
      await AdminService.permanentDeleteDoctor(doc.id);
      setConfirmDelete(null);
      load();
    } catch (err) {
      setError(err?.response?.data?.error || "Failed to delete doctor.");
      setConfirmDelete(null);
    }
  };

  const handleCancelForm = () => { setShowCreate(false); setEditDoctor(null); };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Doctors</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Manage doctors and physician accounts.</p>
        </div>
        <button onClick={openCreate} className="flex items-center gap-2 px-4 py-2 bg-teal-700 text-white rounded-lg text-sm font-medium hover:bg-teal-800 transition-colors">
          <Plus className="h-4 w-4" /> Add Doctor
        </button>
      </div>

      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-4 space-y-3">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="animate-pulse flex items-center gap-4 px-4 py-3">
                <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-16" />
                <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-36" />
                <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-24" />
                <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-24" />
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
        ) : doctors.length === 0 ? (
          <div className="p-8 text-center text-slate-400 dark:text-slate-500 text-sm">No doctors found.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
              <tr>
                <th className="text-left px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">Code</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">Name</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">Department</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">Lab</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
              {doctors.map((doc) => (
                <tr key={doc.id} className="hover:bg-slate-50 dark:hover:bg-slate-800">
                  <td className="px-4 py-3 font-mono text-xs text-slate-700 dark:text-slate-300">{doc.code}</td>
                  <td className="px-4 py-3 font-medium text-slate-800 dark:text-slate-100">{doc.name}</td>
                  <td className="px-4 py-3 text-slate-500 dark:text-slate-400">{doc.department || "—"}</td>
                  <td className="px-4 py-3 text-slate-500 dark:text-slate-400">{doc.lab_name || "—"}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium ${doc.is_active ? "text-green-600" : "text-slate-400 dark:text-slate-500"}`}>
                      {doc.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1 justify-end">
                      <button onClick={() => openEdit(doc)} aria-label={`Edit ${doc.name}`} className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 dark:text-slate-500 hover:text-teal-600">
                        <Edit2 className="h-4 w-4" />
                      </button>
                      {doc.is_active ? (
                        <button onClick={() => setConfirmDeactivate(doc)} aria-label={`Deactivate ${doc.name}`} className="p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-900/30 text-slate-400 dark:text-slate-500 hover:text-red-500">
                          <Power className="h-4 w-4" />
                        </button>
                      ) : (
                        <>
                          <button onClick={() => handleReactivate(doc)} aria-label={`Reactivate ${doc.name}`} title="Reactivate" className="p-1.5 rounded hover:bg-green-50 dark:hover:bg-green-900/30 text-slate-400 dark:text-slate-500 hover:text-green-600 transition-colors">
                            <RotateCcw className="h-4 w-4" />
                          </button>
                          <button onClick={() => setConfirmDelete(doc)} aria-label={`Delete ${doc.name}`} title="Permanently remove" className="p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-900/30 text-slate-400 dark:text-slate-500 hover:text-red-500 transition-colors">
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
        <Modal title="Add Doctor" onClose={() => setShowCreate(false)}>
          <DoctorForm isEdit={false} form={form} setForm={setForm} labs={labs} formError={formError} formLoading={formLoading} onSubmit={handleSubmit} onCancel={handleCancelForm} />
        </Modal>
      )}
      {editDoctor && (
        <Modal title="Edit Doctor" onClose={() => setEditDoctor(null)}>
          <DoctorForm isEdit={true} form={form} setForm={setForm} labs={labs} formError={formError} formLoading={formLoading} onSubmit={handleSubmit} onCancel={handleCancelForm} />
        </Modal>
      )}
      {confirmDeactivate && (
        <ConfirmDialog
          title="Deactivate Doctor"
          message={`Are you sure you want to deactivate "${confirmDeactivate.name}"? They will no longer be able to sign in.`}
          confirmText="Deactivate"
          destructive
          onConfirm={() => handleDeactivate(confirmDeactivate)}
          onCancel={() => setConfirmDeactivate(null)}
        />
      )}
      {confirmDelete && (
        <ConfirmDialog
          title="Permanently Remove Doctor"
          message={`Are you sure you want to permanently remove "${confirmDelete.name}"? This action cannot be undone.`}
          confirmText="Remove Permanently"
          destructive
          onConfirm={() => handlePermanentDelete(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
};

export default AdminDoctors;
