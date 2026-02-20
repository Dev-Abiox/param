import React, { useState, useEffect } from "react";
import { CreditCard, CheckCircle, ArrowUpCircle } from "lucide-react";
import { BillingService } from "@/services/api";

const AdminBilling = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [upgradeLoading, setUpgradeLoading] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [toast, setToast] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await BillingService.getPlan();
      setData(res);
      setSelectedPlan(res?.subscription?.plan?.name || null);
    } catch {
      setError("Failed to load billing data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleUpgrade = async () => {
    if (!selectedPlan || selectedPlan === data?.subscription?.plan?.name) return;
    setUpgradeLoading(true);
    try {
      await BillingService.upgradePlan(selectedPlan);
      setToast({ type: "success", msg: `Plan updated to ${selectedPlan}.` });
      load();
    } catch (err) {
      setToast({ type: "error", msg: err?.response?.data?.error || "Failed to update plan." });
    } finally {
      setUpgradeLoading(false);
      setTimeout(() => setToast(null), 4000);
    }
  };

  if (loading) {
    return <div className="max-w-4xl mx-auto p-8 text-center text-slate-400 dark:text-slate-500">Loading...</div>;
  }

  if (error) {
    return <div className="max-w-4xl mx-auto p-8 text-center text-red-500">{error}</div>;
  }

  const currentPlan = data?.subscription?.plan?.name;
  const availablePlans = data?.available_plans ?? [];
  const status = data?.subscription?.status;

  const STATUS_COLORS = {
    active: "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400",
    trial: "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400",
    cancelled: "bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400",
    past_due: "bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400",
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-sm font-medium ${toast.type === "success" ? "bg-green-600 text-white" : "bg-red-600 text-white"}`}>
          {toast.msg}
        </div>
      )}

      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Billing</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Manage your subscription plan.</p>
      </div>

      {/* Current Subscription Card */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="h-10 w-10 bg-teal-50 dark:bg-teal-900/30 rounded-lg flex items-center justify-center">
            <CreditCard className="h-5 w-5 text-teal-600 dark:text-teal-400" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">Current Subscription</h2>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-4">
          <div>
            <p className="text-xs text-slate-400 dark:text-slate-500 mb-1">Plan</p>
            <p className="font-semibold text-slate-800 dark:text-slate-100 capitalize">{currentPlan || "—"}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400 dark:text-slate-500 mb-1">Status</p>
            <span className={`px-2 py-0.5 rounded-full text-xs font-semibold capitalize ${STATUS_COLORS[status] || "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300"}`}>
              {status || "—"}
            </span>
          </div>
          <div>
            <p className="text-xs text-slate-400 dark:text-slate-500 mb-1">Monthly Limit</p>
            <p className="font-semibold text-slate-800 dark:text-slate-100">
              {data?.subscription?.plan?.monthly_limit === -1 ? "Unlimited" : (data?.subscription?.plan?.monthly_limit?.toLocaleString() ?? "—")}
            </p>
          </div>
        </div>
      </div>

      {/* Plan Picker */}
      {availablePlans.length > 0 && (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm p-6">
          <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2">
            <ArrowUpCircle className="h-5 w-5 text-teal-600 dark:text-teal-400" /> Change Plan
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
            {availablePlans.map((plan) => {
              const isCurrent = plan.name === currentPlan;
              const isSelected = plan.name === selectedPlan;
              return (
                <button
                  key={plan.name}
                  type="button"
                  onClick={() => setSelectedPlan(plan.name)}
                  className={`text-left rounded-xl border-2 p-4 transition-all relative ${
                    isSelected ? "border-teal-500 bg-teal-50 dark:bg-teal-900/30" :
                    "border-slate-200 dark:border-slate-700 hover:border-teal-200"
                  }`}
                >
                  {isCurrent && (
                    <span className="absolute top-2 right-2 px-2 py-0.5 bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-400 text-xs font-semibold rounded-full">
                      Current
                    </span>
                  )}
                  <div className="flex items-center gap-1 mb-1">
                    <p className="font-semibold text-slate-800 dark:text-slate-100 capitalize">{plan.display_name || plan.name}</p>
                    {isSelected && <CheckCircle className="h-4 w-4 text-teal-600 ml-auto" />}
                  </div>
                  <p className="text-lg font-bold text-teal-700 mb-1">
                    {plan.price_monthly === 0 ? "Custom" : `₹${Number(plan.price_monthly).toLocaleString()}`}
                    {plan.price_monthly > 0 && <span className="text-sm font-normal text-slate-400 dark:text-slate-500">/mo</span>}
                  </p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {plan.monthly_limit === -1 ? "Unlimited screenings" : `${Number(plan.monthly_limit).toLocaleString()} screenings/mo`}
                  </p>
                </button>
              );
            })}
          </div>

          <button
            onClick={handleUpgrade}
            disabled={upgradeLoading || !selectedPlan || selectedPlan === currentPlan}
            className="px-6 py-2.5 bg-teal-700 text-white rounded-lg text-sm font-medium hover:bg-teal-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {upgradeLoading ? "Updating..." : selectedPlan === currentPlan ? "No Change" : `Switch to ${selectedPlan || "…"}`}
          </button>
          {selectedPlan !== currentPlan && (
            <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">Changes take effect immediately. Billing adjusted on next cycle.</p>
          )}
        </div>
      )}
    </div>
  );
};

export default AdminBilling;
