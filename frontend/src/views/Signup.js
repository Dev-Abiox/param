import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2, Mail, Lock, User, Eye, EyeOff, CheckCircle, Shield } from "lucide-react";
import { AuthService } from "@/services/api";

const PLANS = [
  {
    key: "starter",
    name: "Starter",
    price: "₹2,999",
    period: "/month",
    limit: "500 screenings/mo",
    features: ["Up to 500 screenings/month", "1 lab", "Up to 5 users", "Email support"],
  },
  {
    key: "professional",
    name: "Professional",
    price: "₹7,999",
    period: "/month",
    limit: "2,000 screenings/mo",
    popular: true,
    features: ["Up to 2,000 screenings/month", "Unlimited labs", "Unlimited users", "Priority support", "Bulk import", "FHIR R4 API"],
  },
  {
    key: "enterprise",
    name: "Enterprise",
    price: "Custom",
    period: "",
    limit: "Unlimited screenings",
    features: ["Unlimited screenings", "Dedicated support", "Custom integrations", "SLA guarantee", "On-premise option"],
  },
];

const PASSWORD_RULES = [
  { test: (pw) => pw.length >= 8, label: "At least 8 characters" },
  { test: (pw) => !/^\d+$/.test(pw), label: "Not entirely numeric" },
  { test: (pw) => !/^(password|12345678|qwerty|abc)/.test(pw.toLowerCase()), label: "Not a common password" },
];

const Signup = ({ onSignup }) => {
  const navigate = useNavigate();
  const [orgName, setOrgName] = useState("");
  const [selectedPlan, setSelectedPlan] = useState("professional");
  const [adminName, setAdminName] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState(null);
  const [tosAccepted, setTosAccepted] = useState(false);
  const [loading, setLoading] = useState(false);

  const passwordValid = adminPassword.length > 0 && PASSWORD_RULES.every((r) => r.test(adminPassword));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!passwordValid) {
      setError("Please fix the password issues below.");
      return;
    }

    setLoading(true);
    try {
      const data = await AuthService.signup({
        orgName,
        adminEmail,
        adminPassword,
        plan: selectedPlan,
        adminName,
        tosAccepted,
      });
      if (onSignup) {
        onSignup(data);
      }
      navigate("/onboarding");
    } catch (err) {
      const raw = err?.response?.data?.error || err?.response?.data?.detail || "Signup failed. Please try again.";
      // Surface friendly message for duplicate email
      if (typeof raw === "string" && raw.toLowerCase().includes("email already exists")) {
        setError("An account with that email already exists. Try signing in instead.");
      } else {
        setError(Array.isArray(raw) ? raw.join(" ") : raw);
      }
    } finally {
      setLoading(false);
    }
  };

  const inputCls = "block w-full px-3 py-2.5 border border-slate-300 dark:border-slate-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100";

  return (
    <div className="min-h-screen bg-slate-100 dark:bg-slate-950 flex flex-col justify-center py-12 px-4">
      <div className="sm:mx-auto sm:w-full sm:max-w-2xl">
        <div className="flex justify-center mb-6">
          <img src="/logo.png?v=17" alt="Clinomic" className="h-16 w-auto" />
        </div>
        <h2 className="text-center text-3xl font-extrabold text-slate-900 dark:text-slate-100">Create your organisation</h2>
        <p className="mt-2 text-center text-sm text-slate-500 dark:text-slate-400">
          Already have an account?{" "}
          <button onClick={() => navigate("/login")} className="font-medium text-teal-600 hover:text-teal-500">
            Sign in
          </button>
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-2xl">
        {/* Trial banner */}
        <div className="mb-4 flex items-center justify-center gap-2 text-sm text-teal-700 dark:text-teal-400 bg-teal-50 dark:bg-teal-900/20 border border-teal-200 dark:border-teal-800 rounded-lg px-4 py-2.5">
          <Shield className="h-4 w-4 flex-shrink-0" />
          <span>All plans include a <strong>14-day free trial</strong>. No credit card required.</span>
        </div>

        <div className="bg-white dark:bg-slate-900 py-8 px-6 shadow sm:rounded-xl border border-slate-200 dark:border-slate-700">
          <form onSubmit={handleSubmit} className="space-y-6">

            {/* Section 1: Organisation */}
            <div>
              <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2">
                <Building2 className="h-5 w-5 text-teal-600" /> Organisation
              </h3>
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Organisation Name</label>
                <input
                  type="text"
                  required
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                  placeholder="Acme Hospital"
                  className={inputCls}
                />
              </div>
            </div>

            {/* Section 2: Plan Picker */}
            <div>
              <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">Choose a Plan</h3>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {PLANS.map((plan) => (
                  <button
                    key={plan.key}
                    type="button"
                    onClick={() => setSelectedPlan(plan.key)}
                    className={`relative text-left rounded-xl border-2 p-4 transition-all ${
                      selectedPlan === plan.key
                        ? "border-teal-500 bg-teal-50 dark:bg-teal-900/20"
                        : "border-slate-200 dark:border-slate-700 hover:border-teal-200"
                    }`}
                  >
                    {plan.popular && (
                      <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 bg-teal-600 text-white text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full">
                        Most Popular
                      </span>
                    )}
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-semibold text-slate-800 dark:text-slate-100">{plan.name}</span>
                      {selectedPlan === plan.key && (
                        <CheckCircle className="h-4 w-4 text-teal-600" />
                      )}
                    </div>
                    <p className="text-xl font-bold text-teal-700 mb-1">
                      {plan.price}<span className="text-sm font-normal text-slate-400">{plan.period}</span>
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">{plan.limit}</p>
                    <ul className="space-y-1">
                      {plan.features.map((f) => (
                        <li key={f} className="text-xs text-slate-600 dark:text-slate-300 flex items-start gap-1">
                          <span className="text-teal-500 mt-0.5">✓</span> {f}
                        </li>
                      ))}
                    </ul>
                  </button>
                ))}
              </div>
              {selectedPlan === "enterprise" && (
                <p className="mt-2 text-xs text-slate-500 dark:text-slate-400 text-center">
                  You'll start on a Professional trial. Our team will reach out to configure your Enterprise plan.
                </p>
              )}
            </div>

            {/* Section 3: Admin Account */}
            <div>
              <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2">
                <User className="h-5 w-5 text-teal-600" /> Administrator Account
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Full Name</label>
                  <input
                    type="text"
                    required
                    value={adminName}
                    onChange={(e) => setAdminName(e.target.value)}
                    placeholder="Dr. Jane Smith"
                    className={inputCls}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                    <span className="flex items-center gap-1"><Mail className="h-4 w-4" /> Email</span>
                  </label>
                  <input
                    type="email"
                    required
                    value={adminEmail}
                    onChange={(e) => setAdminEmail(e.target.value)}
                    placeholder="admin@hospital.com"
                    className={inputCls}
                  />
                  <p className="mt-1 text-xs text-slate-400">This will also be your login email</p>
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                    <span className="flex items-center gap-1"><Lock className="h-4 w-4" /> Password</span>
                  </label>
                  <div className="relative">
                    <input
                      type={showPassword ? "text" : "password"}
                      required
                      value={adminPassword}
                      onChange={(e) => setAdminPassword(e.target.value)}
                      placeholder="Create a strong password"
                      className={`${inputCls} pr-10`}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      className="absolute inset-y-0 right-0 pr-3 flex items-center"
                    >
                      {showPassword ? <EyeOff className="h-4 w-4 text-slate-400 dark:text-slate-500" /> : <Eye className="h-4 w-4 text-slate-400 dark:text-slate-500" />}
                    </button>
                  </div>
                  {adminPassword && (
                    <div className="mt-2 space-y-1">
                      {PASSWORD_RULES.map((rule) => {
                        const passes = rule.test(adminPassword);
                        return (
                          <p key={rule.label} className={`text-xs flex items-center gap-1.5 ${passes ? "text-teal-600" : "text-slate-400"}`}>
                            {passes ? <CheckCircle className="h-3 w-3" /> : <span className="h-3 w-3 rounded-full border border-slate-300 inline-block" />}
                            {rule.label}
                          </p>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Terms of Service */}
            <div className="flex items-start gap-2">
              <input
                id="tos"
                type="checkbox"
                checked={tosAccepted}
                onChange={(e) => setTosAccepted(e.target.checked)}
                className="mt-1 h-4 w-4 text-teal-600 border-slate-300 rounded focus:ring-teal-500"
              />
              <label htmlFor="tos" className="text-sm text-slate-600 dark:text-slate-400">
                I agree to the{" "}
                <a href="/terms" target="_blank" rel="noopener noreferrer" className="text-teal-600 hover:underline">
                  Terms of Service
                </a>{" "}
                and{" "}
                <a href="/privacy" target="_blank" rel="noopener noreferrer" className="text-teal-600 hover:underline">
                  Privacy Policy
                </a>
              </label>
            </div>

            {error && (
              <div className="text-red-600 text-sm bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg px-4 py-3">
                {error}
                {error.includes("already exists") && (
                  <button
                    type="button"
                    onClick={() => navigate("/login")}
                    className="block mt-1 font-medium text-teal-600 hover:text-teal-500 text-sm"
                  >
                    Go to Sign In →
                  </button>
                )}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !orgName || !adminEmail || !adminPassword || !tosAccepted || !passwordValid}
              className="w-full py-3 px-4 bg-teal-700 text-white rounded-lg font-medium text-sm hover:bg-teal-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "Creating organisation..." : "Start Free Trial"}
            </button>
          </form>
        </div>

        <div className="mt-4 text-center text-xs text-slate-400 dark:text-slate-500">
          <p>HIPAA Compliant · FDA 21 CFR Part 11 Ready</p>
        </div>
      </div>
    </div>
  );
};

export default Signup;
