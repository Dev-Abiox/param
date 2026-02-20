import React, { useState, useEffect } from "react";
import { Plus, Edit2, Power, X } from "lucide-react";
import { AdminService } from "@/services/api";

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

const AdminDoctors = () => {
  const [doctors, setDoctors] = useState([]);
  const [labs, setLabs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editDoctor, setEditDoctor] = useState(null);
  const [formError, setFormError] = useState(null);
  const [formLoading, setFormLoading] = useState(false);

  const emptyForm = { code: "", name: "", department: "", specialization: "", email: "", lab_id: "" };
  const [form, setForm] = useState(emptyForm);

  const load = async () => {
    setLoading(true);
    try {
      const [docData, labData] = await Promise.all([
        AdminService.getDoctors(),
        AdminService.getLabs(),
      ]);
      setDoctors(docData);
      setLabs(labData.filter((l) => l.is_active));
    } catch {
      // silent
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
    if (!window.confirm(`Deactivate Dr. ${doc.name}?`)) return;
    try {
      await AdminService.deactivateDoctor(doc.id);
      load();
    } catch {
      // silent
    }
  };

  const inputCls = "block w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white text-slate-900";

  const DoctorForm = ({ isEdit }) => (
    <form onSubmit={handleSubmit} className="space-y-4">
      {!isEdit && (
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">Doctor Code</label>
          <input required type="text" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} className={inputCls} placeholder="D001" />
        </div>
      )}
      <div>
        <label className="block text-xs font-medium text-slate-700 mb-1">Full Name</label>
        <input required type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={inputCls} placeholder="Dr. Jane Smith" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">Department</label>
          <input type="text" value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} className={inputCls} placeholder="Haematology" />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">Specialization</label>
          <input type="text" value={form.specialization} onChange={(e) => setForm({ ...form, specialization: e.target.value })} className={inputCls} placeholder="B12 Disorders" />
        </div>
      </div>
      <div>
        <label className="block text-xs font-medium text-slate-700 mb-1">Email</label>
        <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className={inputCls} placeholder="doctor@hospital.com" />
      </div>
      <div>
        <label className="block text-xs font-medium text-slate-700 mb-1">Lab</label>
        <select required value={form.lab_id} onChange={(e) => setForm({ ...form, lab_id: e.target.value })} className={inputCls}>
          <option value="">Select a lab…</option>
          {labs.map((l) => <option key={l.id} value={l.id}>{l.name} ({l.code})</option>)}
        </select>
      </div>
      {formError && (
        <p className="text-xs text-red-600 bg-red-50 px-3 py-2 rounded border border-red-200">{formError}</p>
      )}
      <div className="flex gap-3">
        <button type="button" onClick={() => { setShowCreate(false); setEditDoctor(null); }} className="flex-1 py-2 border border-slate-300 rounded-lg text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
        <button type="submit" disabled={formLoading} className="flex-1 py-2 bg-teal-700 text-white rounded-lg text-sm font-medium hover:bg-teal-800 disabled:opacity-50">
          {formLoading ? "Saving..." : isEdit ? "Save Changes" : "Create Doctor"}
        </button>
      </div>
    </form>
  );

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Doctors</h1>
          <p className="text-sm text-slate-500 mt-1">Manage doctors and physician accounts.</p>
        </div>
        <button onClick={openCreate} className="flex items-center gap-2 px-4 py-2 bg-teal-700 text-white rounded-lg text-sm font-medium hover:bg-teal-800 transition-colors">
          <Plus className="h-4 w-4" /> Add Doctor
        </button>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-slate-400 text-sm">Loading...</div>
        ) : doctors.length === 0 ? (
          <div className="p-8 text-center text-slate-400 text-sm">No doctors found.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Code</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Name</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Department</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Lab</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {doctors.map((doc) => (
                <tr key={doc.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-mono text-xs text-slate-700">{doc.code}</td>
                  <td className="px-4 py-3 font-medium text-slate-800">{doc.name}</td>
                  <td className="px-4 py-3 text-slate-500">{doc.department || "—"}</td>
                  <td className="px-4 py-3 text-slate-500">{doc.lab_name || "—"}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium ${doc.is_active ? "text-green-600" : "text-slate-400"}`}>
                      {doc.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1 justify-end">
                      <button onClick={() => openEdit(doc)} className="p-1.5 rounded hover:bg-slate-100 text-slate-400 hover:text-teal-600">
                        <Edit2 className="h-4 w-4" />
                      </button>
                      {doc.is_active && (
                        <button onClick={() => handleDeactivate(doc)} className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-500">
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
        <Modal title="Add Doctor" onClose={() => setShowCreate(false)}>
          <DoctorForm isEdit={false} />
        </Modal>
      )}
      {editDoctor && (
        <Modal title="Edit Doctor" onClose={() => setEditDoctor(null)}>
          <DoctorForm isEdit={true} />
        </Modal>
      )}
    </div>
  );
};

export default AdminDoctors;
