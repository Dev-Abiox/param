import React, { useState, useEffect } from "react";
import { CreditCard, CheckCircle, ArrowUpCircle, TrendingUp, AlertTriangle, Zap } from "lucide-react";
import { BillingService } from "@/services/api";

/* ─── helpers ─────────────────────────────────────────── */
const pct = (used, limit) => {
  if (!limit || limit === -1) return 0;
  return Math.min(100, Math.round((used / limit) * 100));
};

const barColor = (p) => {
  if (p >= 90) return { bar: "bg-red-500", text: "text-red-600 dark:text-red-400", bg: "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800" };
  if (p >= 70) return { bar: "bg-amber-500", text: "text-amber-600 dark:text-amber-400", bg: "bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800" };
  return { bar: "bg-teal-500", text: "text-teal-600 dark:text-teal-400", bg: "bg-teal-50 dark:bg-teal-900/20 border-teal-200 dark:border-teal-800" };
};

const fmtINR = (n) =>
  n == null ? "—" : `₹${Number(n).toLocaleString("en-IN")}`;

const STATUS_PILL = {
  ACTIVE:    "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400",
  TRIAL:     "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400",
  EXPIRED:   "bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400",
  SUSPENDED: "bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400",
  CANCELLED: "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400",
  PAST_DUE:  "bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400",
};

const loadRazorpay = () => {
  return new Promise((resolve) => {
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
};

/* ─── component ───────────────────────────────────────── */
const AdminBilling = () => {
  const [planData, setPlanData]       = useState(null);
  const [usageData, setUsageData]     = useState(null);
  const [loading, setLoading]         = useState(true);
  const [upgradeLoading, setUpgradeLoading] = useState(false);
  const [selectedPlan, setSelectedPlan]     = useState(null);
  const [toast, setToast]             = useState(null);
  const [error, setError]             = useState(null);

  const showToast = (type, msg) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 4500);
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [plan, usage] = await Promise.all([
        BillingService.getPlan(),
        BillingService.getUsage(),
      ]);
      setPlanData(plan);
      setUsageData(usage);
      setSelectedPlan(plan?.subscription?.plan?.name || null);
    } catch {
      setError("Failed to load billing information. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleUpgrade = async () => {
    if (!selectedPlan || selectedPlan === planData?.subscription?.plan?.name) return;
    setUpgradeLoading(true);
    
    try {
      const isLoaded = await loadRazorpay();
      if (!isLoaded) {
        showToast("error", "Failed to load payment gateway. Please check your connection.");
        setUpgradeLoading(false);
        return;
      }
      
      const result = await BillingService.initiateUpgrade(selectedPlan);
      if (!result.razorpay_key_id) {
        showToast("error", "Payment gateway is not configured. Please contact support.");
        setUpgradeLoading(false);
        return;
      }
      const options = {
        key: result.razorpay_key_id,
        subscription_id: result.subscription_id,
        name: "Clinomic",
        description: `Upgrade to ${result.display_name}`,
        handler: () => {
          showToast("success", `Payment successful! Upgrading to ${result.display_name}.`);
          setTimeout(() => load(), 2000);
        },
        modal: {
          ondismiss: () => {
            showToast("error", "Payment cancelled.");
            setUpgradeLoading(false);
          },
        },
        theme: { color: "#0D9488" },
      };
      const rzp = new window.Razorpay(options);
      rzp.open();
    } catch (err) {
      showToast("error", err?.response?.data?.error || "Failed to initiate upgrade.");
      setUpgradeLoading(false);
    }
  };

  /* ── loading / error states ── */
  if (loading) {
    return (
      <div className="max-w-4xl mx-auto p-8 space-y-4 animate-pulse">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-32 bg-slate-100 dark:bg-slate-800 rounded-xl" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto p-8 text-center">
        <p className="text-red-500 mb-4">{error}</p>
        <button onClick={load} className="px-4 py-2 bg-teal-600 text-white rounded-lg text-sm hover:bg-teal-700">
          Try again
        </button>
      </div>
    );
  }

  /* ── derived values ── */
  const sub          = planData?.subscription ?? {};
  const plan         = sub.plan ?? {};
  const status       = (sub.status ?? "").toUpperCase();
  const availPlans   = planData?.available_plans ?? [];
  const currentPlan  = plan.name;
  const monthlyLimit = plan.monthly_limit;
  const monthlyPrice = plan.price_monthly;

  const usedCount    = usageData?.current_period_count ?? sub.current_period_count ?? 0;
  const usedPct      = pct(usedCount, monthlyLimit);
  const colors       = barColor(usedPct);

  const periodStart  = usageData?.period_start || sub.current_period_start;
  const periodEnd    = usageData?.period_end   || sub.current_period_end;
  const trialEnd     = sub.trial_end;
  const history      = usageData?.history ?? [];

  const daysLeft = (() => {
    if (!periodEnd) return null;
    const diff = Math.ceil((new Date(periodEnd) - new Date()) / 86400000);
    return diff > 0 ? diff : 0;
  })();

  const trialDaysLeft = (() => {
    if (!trialEnd || status !== "TRIAL") return null;
    const diff = Math.ceil((new Date(trialEnd) - new Date()) / 86400000);
    return diff > 0 ? diff : 0;
  })();

  const fmtDate = (d) =>
    d ? new Date(d).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "—";

  /* ── render ── */
  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Toast */}
      {toast && (
        <div
          className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-sm font-medium transition-all ${
            toast.type === "success" ? "bg-green-600 text-white" : "bg-red-600 text-white"
          }`}
        >
          {toast.msg}
        </div>
      )}

      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Billing &amp; Usage</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Manage your subscription plan and monitor usage.
        </p>
      </div>

      {/* Trial warning banner */}
      {status === "TRIAL" && (
        <div className="flex items-start gap-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-xl px-4 py-3">
          <AlertTriangle className="h-5 w-5 text-amber-500 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-amber-800 dark:text-amber-300">
              Trial period — {trialDaysLeft != null ? `${trialDaysLeft} day${trialDaysLeft !== 1 ? "s" : ""} remaining` : "ending soon"}
            </p>
            <p className="text-xs text-amber-700 dark:text-amber-400 mt-0.5">
              Upgrade before your trial ends to avoid interruption.{trialEnd ? ` Trial ends ${fmtDate(trialEnd)}.` : ""}
            </p>
          </div>
        </div>
      )}

      {/* Expired trial banner */}
      {status === "EXPIRED" && (
        <div className="flex items-start gap-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl px-4 py-3">
          <AlertTriangle className="h-5 w-5 text-red-500 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-red-800 dark:text-red-300">
              Your trial has expired
            </p>
            <p className="text-xs text-red-700 dark:text-red-400 mt-0.5">
              Upgrade to a paid plan below to continue running screenings. Your existing data is safe.
            </p>
          </div>
        </div>
      )}

      {/* Suspended warning banner */}
      {status === "SUSPENDED" && (
        <div className="flex items-start gap-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl px-4 py-3">
          <AlertTriangle className="h-5 w-5 text-red-500 mt-0.5 shrink-0" />
          <p className="text-sm font-semibold text-red-800 dark:text-red-300">
            Your account is suspended. Contact support to reactivate.
          </p>
        </div>
      )}

      {/* ── Current plan card ── */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm p-6">
        <div className="flex items-center gap-3 mb-5">
          <div className="h-10 w-10 bg-teal-50 dark:bg-teal-900/30 rounded-lg flex items-center justify-center">
            <CreditCard className="h-5 w-5 text-teal-600 dark:text-teal-400" />
          </div>
          <div className="flex-1">
            <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">Current Plan</h2>
          </div>
          <span className={`px-2.5 py-1 rounded-full text-xs font-semibold capitalize ${STATUS_PILL[status] || "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400"}`}>
            {status || "—"}
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-5">
          <div>
            <p className="text-xs text-slate-400 dark:text-slate-500 mb-1 uppercase tracking-wide">Plan</p>
            <p className="font-semibold text-slate-800 dark:text-slate-100 capitalize">
              {plan.display_name || currentPlan || "—"}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-400 dark:text-slate-500 mb-1 uppercase tracking-wide">Price</p>
            <p className="font-semibold text-slate-800 dark:text-slate-100">
              {monthlyPrice == null ? "—" : monthlyPrice === 0 ? "Custom" : `${fmtINR(monthlyPrice)}/mo`}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-400 dark:text-slate-500 mb-1 uppercase tracking-wide">Monthly limit</p>
            <p className="font-semibold text-slate-800 dark:text-slate-100">
              {monthlyLimit === -1 ? "Unlimited" : (monthlyLimit?.toLocaleString("en-IN") ?? "—")} screenings
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-400 dark:text-slate-500 mb-1 uppercase tracking-wide">Period</p>
            <p className="font-semibold text-slate-800 dark:text-slate-100 text-xs leading-relaxed">
              {fmtDate(periodStart)} –<br />{fmtDate(periodEnd)}
            </p>
          </div>
        </div>
      </div>

      {/* ── Usage this period ── */}
      <div className={`bg-white dark:bg-slate-900 rounded-xl border shadow-sm p-6 ${usedPct >= 90 ? "border-red-200 dark:border-red-800" : usedPct >= 70 ? "border-amber-200 dark:border-amber-800" : "border-slate-200 dark:border-slate-700"}`}>
        <div className="flex items-center gap-3 mb-5">
          <div className="h-10 w-10 bg-teal-50 dark:bg-teal-900/30 rounded-lg flex items-center justify-center">
            <TrendingUp className="h-5 w-5 text-teal-600 dark:text-teal-400" />
          </div>
          <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">Usage This Period</h2>
          {usedPct >= 90 && (
            <span className="ml-auto flex items-center gap-1 text-xs font-semibold text-red-600 dark:text-red-400">
              <AlertTriangle className="h-3.5 w-3.5" /> Near limit
            </span>
          )}
        </div>

        {monthlyLimit === -1 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            <span className="font-semibold text-slate-800 dark:text-slate-100">{usedCount.toLocaleString("en-IN")}</span> screenings used · Unlimited plan
          </p>
        ) : (
          <>
            <div className="flex items-end justify-between mb-2">
              <span className={`text-2xl font-bold ${colors.text}`}>
                {usedCount.toLocaleString("en-IN")}
                <span className="text-base font-normal text-slate-400 dark:text-slate-500 ml-1">
                  / {monthlyLimit?.toLocaleString("en-IN")} screenings
                </span>
              </span>
              <span className={`text-sm font-semibold ${colors.text}`}>{usedPct}%</span>
            </div>

            {/* Progress bar */}
            <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-3 overflow-hidden">
              <div
                className={`h-3 rounded-full transition-all duration-500 ${colors.bar}`}
                style={{ width: `${usedPct}%` }}
              />
            </div>

            <div className="flex items-center justify-between mt-2 text-xs text-slate-400 dark:text-slate-500">
              <span>{Math.max(0, monthlyLimit - usedCount).toLocaleString("en-IN")} screenings remaining</span>
              {daysLeft != null && (
                <span>Resets in {daysLeft} day{daysLeft !== 1 ? "s" : ""}</span>
              )}
            </div>
          </>
        )}
      </div>

      {/* ── Usage history ── */}
      {history.length > 0 && (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm p-6">
          <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100 mb-5">Usage History</h2>
          <HistoryBars history={history} limit={monthlyLimit} />
        </div>
      )}

      {/* ── Plan picker / upgrade ── */}
      {availPlans.length > 0 && (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm p-6">
          <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100 mb-1 flex items-center gap-2">
            <ArrowUpCircle className="h-5 w-5 text-teal-600 dark:text-teal-400" /> Available Plans
          </h2>
          <p className="text-xs text-slate-400 dark:text-slate-500 mb-5">Select a plan and click the button below to switch.</p>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
            {availPlans.map((p) => {
              const isCurrent  = p.name === currentPlan;
              const isSelected = p.name === selectedPlan;
              return (
                <button
                  key={p.name}
                  type="button"
                  onClick={() => setSelectedPlan(p.name)}
                  className={`text-left rounded-xl border-2 p-4 transition-all relative ${
                    isSelected
                      ? "border-teal-500 bg-teal-50 dark:bg-teal-900/20"
                      : "border-slate-200 dark:border-slate-700 hover:border-teal-200 dark:hover:border-teal-700"
                  }`}
                >
                  {isCurrent && (
                    <span className="absolute top-2 right-2 px-2 py-0.5 bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-400 text-xs font-semibold rounded-full">
                      Current
                    </span>
                  )}
                  <div className="flex items-center gap-1 mb-1 pr-14">
                    <p className="font-semibold text-slate-800 dark:text-slate-100 capitalize">
                      {p.display_name || p.name}
                    </p>
                    {isSelected && !isCurrent && <CheckCircle className="h-4 w-4 text-teal-600 dark:text-teal-400 ml-auto shrink-0" />}
                  </div>
                  <p className="text-xl font-bold text-teal-700 dark:text-teal-400 mb-1">
                    {p.price_monthly === 0 ? "Custom" : fmtINR(p.price_monthly)}
                    {p.price_monthly > 0 && (
                      <span className="text-sm font-normal text-slate-400 dark:text-slate-500">/mo</span>
                    )}
                  </p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1">
                    <Zap className="h-3 w-3" />
                    {p.monthly_limit === -1
                      ? "Unlimited screenings"
                      : `${Number(p.monthly_limit).toLocaleString("en-IN")} screenings/mo`}
                  </p>
                  {p.features && (
                    <ul className="mt-2 space-y-0.5">
                      {(Array.isArray(p.features) ? p.features : []).slice(0, 3).map((f, i) => (
                        <li key={i} className="text-xs text-slate-400 dark:text-slate-500 flex items-center gap-1">
                          <CheckCircle className="h-3 w-3 text-teal-500 shrink-0" /> {f}
                        </li>
                      ))}
                    </ul>
                  )}
                </button>
              );
            })}
          </div>

          {/* CTA */}
          {(() => {
            const selObj     = availPlans.find((p) => p.name === selectedPlan);
            const isEnterprise = selObj && Number(selObj.price_monthly) === 0;
            const isChanged    = selectedPlan && selectedPlan !== currentPlan;

            if (isChanged && isEnterprise) {
              return (
                <a
                  href="mailto:sales@clinomiclabs.com?subject=Enterprise%20Plan%20Inquiry"
                  className="inline-block px-6 py-2.5 bg-purple-700 text-white rounded-lg text-sm font-medium hover:bg-purple-800 transition-colors"
                >
                  Contact Sales
                </a>
              );
            }
            return (
              <button
                onClick={handleUpgrade}
                disabled={upgradeLoading || !selectedPlan || selectedPlan === currentPlan}
                className="px-6 py-2.5 bg-teal-700 text-white rounded-lg text-sm font-medium hover:bg-teal-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {upgradeLoading
                  ? "Processing…"
                  : selectedPlan === currentPlan
                  ? "Current plan selected"
                  : `Switch to ${selObj?.display_name || selectedPlan || "…"}`}
              </button>
            );
          })()}
          {selectedPlan !== currentPlan && (
            <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
              Changes take effect immediately. Billing is adjusted on your next cycle.
            </p>
          )}
        </div>
      )}
    </div>
  );
};

/* ─── Usage history bar chart ─────────────────────────── */
const HistoryBars = ({ history, limit }) => {
  if (!history.length) return null;

  const maxVal = Math.max(...history.map((h) => h.count ?? 0), 1);

  return (
    <div className="flex items-end gap-2 h-32">
      {history.map((h, i) => {
        const val   = h.count ?? 0;
        const p     = pct(val, limit !== -1 ? limit : maxVal);
        const heightPct = Math.max(4, Math.round((val / maxVal) * 100));
        const col   = barColor(p);
        const label = h.period_start
          ? new Date(h.period_start).toLocaleDateString("en-IN", { month: "short" })
          : `M${i + 1}`;
        return (
          <div key={i} className="flex-1 flex flex-col items-center gap-1 group">
            <div className="relative w-full flex items-end justify-center" style={{ height: "96px" }}>
              <div
                className={`w-full rounded-t-md ${col.bar} opacity-80 group-hover:opacity-100 transition-opacity`}
                style={{ height: `${heightPct}%` }}
                title={`${label}: ${val.toLocaleString("en-IN")} screenings`}
              />
            </div>
            <span className="text-xs text-slate-400 dark:text-slate-500 truncate w-full text-center">{label}</span>
          </div>
        );
      })}
    </div>
  );
};

export default AdminBilling;
