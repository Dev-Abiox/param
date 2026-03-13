import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2, ArrowLeft, CheckCircle } from "lucide-react";
import { PlatformService } from "@/services/PlatformService";

const PLANS = [
  { value: "starter",      label: "Starter",      desc: "500 screenings/mo · Coming Soon" },
  { value: "professional", label: "Professional",  desc: "2,000 screenings/mo · Coming Soon" },
  { value: "enterprise",   label: "Enterprise",    desc: "Unlimited · Coming Soon" },
];

const PlatformCreateOrg = () => {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    org_name: "",
    admin_name: "",
    admin_email: "",
    plan_name: "starter",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const handleChange = (e) =>
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const result = await PlatformService.createOrg(form);
      setSuccess(result);
    } catch (err) {
      const msg =
        err?.response?.data?.error ||
        Object.values(err?.response?.data?.errors || {}).flat().join(" ") ||
        "Failed to create organisation.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="p-6 max-w-xl mx-auto">
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-8 text-center space-y-4">
          <div className="flex justify-center">
            <CheckCircle className="h-16 w-16 text-teal-500" />
          </div>
          <h2 className="text-xl font-bold text-slate-800 dark:text-slate-100">Lab Created!</h2>
          <p className="text-slate-600 dark:text-slate-300">
            <strong>{success.name}</strong> has been set up on the <strong>{success.plan}</strong> plan.
          </p>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Login credentials have been sent to <strong>{success.admin_email}</strong>.
          </p>
          <div className="flex gap-3 justify-center pt-2">
            <button
              onClick={() => navigate(`/platform-admin/orgs/${success.schema_name}`)}
              className="px-4 py-2 bg-teal-600 text-white text-sm font-medium rounded-lg hover:bg-teal-700"
            >
              View Lab
            </button>
            <button
              onClick={() => navigate("/platform-admin/orgs")}
              className="px-4 py-2 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 text-sm rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700"
            >
              All Labs
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate("/platform-admin/orgs")}
          className="p-2 text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Create New Lab</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            The lab admin will receive login credentials via email.
          </p>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 rounded-lg p-4 text-sm">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6 space-y-5">
        {/* Org name */}
        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
            Organisation Name *
          </label>
          <div className="relative">
            <Building2 className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <input
              name="org_name"
              value={form.org_name}
              onChange={handleChange}
              required
              placeholder="City Diagnostics Lab"
              className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
          </div>
        </div>

        {/* Admin name */}
        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
            Admin Full Name *
          </label>
          <input
            name="admin_name"
            value={form.admin_name}
            onChange={handleChange}
            required
            placeholder="Dr. Priya Sharma"
            className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-teal-500"
          />
        </div>

        {/* Admin email */}
        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
            Admin Email *
          </label>
          <input
            name="admin_email"
            type="email"
            value={form.admin_email}
            onChange={handleChange}
            required
            placeholder="admin@citydiag.com"
            className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-teal-500"
          />
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
            Login credentials will be sent to this address.
          </p>
        </div>

        {/* Plan */}
        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
            Plan *
          </label>
          <div className="space-y-2">
            {PLANS.map((plan) => (
              <label
                key={plan.value}
                className={`flex items-center gap-3 p-3 border rounded-lg cursor-pointer transition-colors ${
                  form.plan_name === plan.value
                    ? "border-teal-500 bg-teal-50 dark:bg-teal-900/20"
                    : "border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/30"
                }`}
              >
                <input
                  type="radio"
                  name="plan_name"
                  value={plan.value}
                  checked={form.plan_name === plan.value}
                  onChange={handleChange}
                  className="text-teal-600"
                />
                <div>
                  <p className="text-sm font-medium text-slate-700 dark:text-slate-300">{plan.label}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">{plan.desc}</p>
                </div>
              </label>
            ))}
          </div>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full py-2.5 bg-teal-600 text-white text-sm font-medium rounded-lg hover:bg-teal-700 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {loading ? "Creating…" : "Create Lab & Send Credentials"}
        </button>
      </form>
    </div>
  );
};

export default PlatformCreateOrg;
