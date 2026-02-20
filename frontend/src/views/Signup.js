import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2, Mail, Lock, User, Eye, EyeOff, CheckCircle } from "lucide-react";
import { AuthService } from "@/services/api";

const PLANS = [
  {
    key: "starter",
    name: "Starter",
    price: "₹2,999",
    limit: "500 screenings/mo",
    features: ["Up to 500 screenings/month", "1 lab", "Up to 5 users", "Email support"],
  },
  {
    key: "professional",
    name: "Professional",
    price: "₹7,999",
    limit: "2,000 screenings/mo",
    features: ["Up to 2,000 screenings/month", "Unlimited labs", "Unlimited users", "Priority support", "Bulk import", "FHIR R4 API"],
  },
  {
    key: "enterprise",
    name: "Enterprise",
    price: "Custom",
    limit: "Unlimited screenings",
    features: ["Unlimited screenings", "Dedicated support", "Custom integrations", "SLA guarantee", "On-premise option"],
  },
];

const Signup = ({ onSignup }) => {
  const navigate = useNavigate();
  const [step, setStep] = useState(1); // 1: org+plan, 2: admin account
  const [orgName, setOrgName] = useState("");
  const [selectedPlan, setSelectedPlan] = useState("starter");
  const [adminName, setAdminName] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const slug = orgName.toLowerCase().replace(/[^a-z0-9]/g, "_").replace(/_+/g, "_").slice(0, 40);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (adminPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (adminPassword.length < 8) {
      setError("Password must be at least 8 characters.");
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
      });
      if (onSignup) {
        onSignup(data);
      }
      navigate("/onboarding");
    } catch (err) {
      const msg = err?.response?.data?.error || err?.response?.data?.detail || "Signup failed. Please try again.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-100 flex flex-col justify-center py-12 px-4">
      <div className="sm:mx-auto sm:w-full sm:max-w-2xl">
        <div className="flex justify-center mb-6">
          <img src="/logo.png?v=17" alt="Clinomic" className="h-16 w-auto" />
        </div>
        <h2 className="text-center text-3xl font-extrabold text-slate-900">Create your organisation</h2>
        <p className="mt-2 text-center text-sm text-slate-500">
          Already have an account?{" "}
          <button onClick={() => navigate("/login")} className="font-medium text-teal-600 hover:text-teal-500">
            Sign in
          </button>
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-2xl">
        <div className="bg-white py-8 px-6 shadow sm:rounded-xl border border-slate-200">
          <form onSubmit={handleSubmit} className="space-y-6">

            {/* Section 1: Organisation */}
            <div>
              <h3 className="text-lg font-semibold text-slate-800 mb-4 flex items-center gap-2">
                <Building2 className="h-5 w-5 text-teal-600" /> Organisation
              </h3>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Organisation Name</label>
                <input
                  type="text"
                  required
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                  placeholder="Acme Hospital"
                  className="block w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white text-slate-900"
                />
                {orgName && (
                  <p className="mt-1 text-xs text-slate-400">
                    Tenant ID: <span className="font-mono text-teal-600">{slug}</span>
                  </p>
                )}
              </div>
            </div>

            {/* Section 2: Plan Picker */}
            <div>
              <h3 className="text-lg font-semibold text-slate-800 mb-4">Choose a Plan</h3>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {PLANS.map((plan) => (
                  <button
                    key={plan.key}
                    type="button"
                    onClick={() => setSelectedPlan(plan.key)}
                    className={`text-left rounded-xl border-2 p-4 transition-all ${
                      selectedPlan === plan.key
                        ? "border-teal-500 bg-teal-50"
                        : "border-slate-200 hover:border-teal-200"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-semibold text-slate-800">{plan.name}</span>
                      {selectedPlan === plan.key && (
                        <CheckCircle className="h-4 w-4 text-teal-600" />
                      )}
                    </div>
                    <p className="text-xl font-bold text-teal-700 mb-1">{plan.price}</p>
                    <p className="text-xs text-slate-500 mb-3">{plan.limit}</p>
                    <ul className="space-y-1">
                      {plan.features.map((f) => (
                        <li key={f} className="text-xs text-slate-600 flex items-start gap-1">
                          <span className="text-teal-500 mt-0.5">✓</span> {f}
                        </li>
                      ))}
                    </ul>
                  </button>
                ))}
              </div>
            </div>

            {/* Section 3: Admin Account */}
            <div>
              <h3 className="text-lg font-semibold text-slate-800 mb-4 flex items-center gap-2">
                <User className="h-5 w-5 text-teal-600" /> Administrator Account
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Full Name</label>
                  <input
                    type="text"
                    required
                    value={adminName}
                    onChange={(e) => setAdminName(e.target.value)}
                    placeholder="Dr. Jane Smith"
                    className="block w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white text-slate-900"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    <span className="flex items-center gap-1"><Mail className="h-4 w-4" /> Email</span>
                  </label>
                  <input
                    type="email"
                    required
                    value={adminEmail}
                    onChange={(e) => setAdminEmail(e.target.value)}
                    placeholder="admin@hospital.com"
                    className="block w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white text-slate-900"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    <span className="flex items-center gap-1"><Lock className="h-4 w-4" /> Password</span>
                  </label>
                  <div className="relative">
                    <input
                      type={showPassword ? "text" : "password"}
                      required
                      value={adminPassword}
                      onChange={(e) => setAdminPassword(e.target.value)}
                      placeholder="Min 8 characters"
                      className="block w-full px-3 py-2.5 pr-10 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white text-slate-900"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute inset-y-0 right-0 pr-3 flex items-center"
                    >
                      {showPassword ? <EyeOff className="h-4 w-4 text-slate-400" /> : <Eye className="h-4 w-4 text-slate-400" />}
                    </button>
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Confirm Password</label>
                  <input
                    type="password"
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Re-enter password"
                    className="block w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white text-slate-900"
                  />
                </div>
              </div>
            </div>

            {error && (
              <div className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg px-4 py-3">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !orgName || !adminEmail || !adminPassword}
              className="w-full py-3 px-4 bg-teal-700 text-white rounded-lg font-medium text-sm hover:bg-teal-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "Creating organisation..." : "Create Organisation & Sign In"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default Signup;
