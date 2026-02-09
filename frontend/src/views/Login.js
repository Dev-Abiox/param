import React, { useState } from "react";
import { Lock, User, ArrowLeft, Mail, CheckCircle, Shield, Smartphone, Key, Eye, EyeOff } from "lucide-react";
import { AuthService } from "@/services/api";

const Login = ({ onLogin, onMFARequired, isLoading, error }) => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [view, setView] = useState("login"); // login, forgot_password, mfa_challenge
  const [resetStatus, setResetStatus] = useState("idle");

  // MFA state
  const [mfaCode, setMfaCode] = useState("");
  const [mfaPendingToken, setMfaPendingToken] = useState(null);
  const [mfaError, setMfaError] = useState(null);
  const [mfaLoading, setMfaLoading] = useState(false);
  const [pendingUser, setPendingUser] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMfaError(null);

    try {
      const result = await onLogin(username, password);

      // Check if MFA is required
      if (result && result.mfaRequired) {
        setMfaPendingToken(result.mfaPendingToken);
        setPendingUser({ id: result.id, name: result.name, role: result.role });
        setView("mfa_challenge");
      }
    } catch (err) {
      // Error handled by parent
    }
  };

  const handleMFASubmit = async (e) => {
    e.preventDefault();
    setMfaLoading(true);
    setMfaError(null);

    try {
      const user = await AuthService.verifyMFA(mfaPendingToken, mfaCode);
      // Call parent's success handler
      if (onMFARequired) {
        onMFARequired(user);
      }
    } catch (err) {
      setMfaError("Invalid verification code. Please try again.");
    } finally {
      setMfaLoading(false);
    }
  };

  const handleBackToLogin = () => {
    setView("login");
    setMfaCode("");
    setMfaPendingToken(null);
    setMfaError(null);
    setPendingUser(null);
  };

  const handleResetSubmit = (e) => {
    e.preventDefault();
    setResetStatus("loading");
    setTimeout(() => setResetStatus("success"), 1500);
  };

  const toggleView = () => {
    setView(view === "login" ? "forgot_password" : "login");
    setResetStatus("idle");
  };

  const fillDemoCredentials = (user, pass) => {
    setUsername(user);
    setPassword(pass);
  };

  // MFA Challenge View
  if (view === "mfa_challenge") {
    return (
      <div data-testid="mfa-challenge-page" className="min-h-screen bg-slate-100 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
        <div className="sm:mx-auto sm:w-full sm:max-w-md">
          <div className="flex justify-center">
            <div className="h-16 w-16 bg-teal-600 rounded-xl flex items-center justify-center shadow-lg">
              <Shield className="h-10 w-10 text-white" />
            </div>
          </div>
          <h2 className="mt-6 text-center text-2xl font-bold text-slate-900">Two-Factor Authentication</h2>
          <p className="mt-2 text-center text-sm text-slate-600">
            Welcome back, <span className="font-medium">{pendingUser?.name || pendingUser?.id}</span>
          </p>
        </div>

        <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
          <div className="bg-white py-8 px-4 shadow sm:rounded-lg sm:px-10 border border-slate-200">
            <div className="mb-6 flex items-center justify-center space-x-2 text-slate-500">
              <Smartphone className="h-5 w-5" />
              <span className="text-sm">Enter the code from your authenticator app</span>
            </div>

            <form className="space-y-6" onSubmit={handleMFASubmit}>
              <div>
                <label htmlFor="mfa-code" className="block text-sm font-medium text-slate-700 text-center mb-2">
                  Verification Code
                </label>
                <input
                  data-testid="mfa-code-input"
                  id="mfa-code"
                  name="mfa-code"
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  required
                  autoFocus
                  autoComplete="one-time-code"
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, ""))}
                  className="block w-full text-center text-2xl tracking-[0.5em] font-mono py-3 border-slate-300 rounded-md focus:ring-teal-500 focus:border-teal-500 border bg-white text-black"
                  placeholder="000000"
                />
              </div>

              {mfaError && (
                <div data-testid="mfa-error" className="text-red-600 text-sm bg-red-50 p-2 rounded border border-red-100 text-center">
                  {mfaError}
                </div>
              )}

              <div>
                <button
                  data-testid="mfa-submit-button"
                  type="submit"
                  disabled={mfaLoading || mfaCode.length !== 6}
                  className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-teal-700 hover:bg-teal-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-teal-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {mfaLoading ? "Verifying..." : "Verify & Sign In"}
                </button>
              </div>
            </form>

            <div className="mt-6 border-t border-slate-200 pt-4">
              <div className="text-center">
                <button
                  data-testid="use-backup-code-button"
                  type="button"
                  className="text-sm text-slate-500 hover:text-teal-600"
                >
                  <Key className="h-4 w-4 inline mr-1" />
                  Use a backup code instead
                </button>
              </div>
              <div className="mt-4 flex items-center justify-center">
                <button
                  data-testid="mfa-back-button"
                  type="button"
                  onClick={handleBackToLogin}
                  className="flex items-center text-sm font-medium text-slate-600 hover:text-teal-600"
                >
                  <ArrowLeft className="h-4 w-4 mr-1" /> Back to Sign In
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="login-page" className="min-h-screen bg-slate-100 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center">
          <img src="/logo.png" alt="Clinomic Labs Logo" className="h-20 w-auto" />
        </div>
        <h2 className="mt-6 text-center text-3xl font-extrabold text-slate-900 tracking-tight">Clinomic Labs</h2>
        <p className="mt-2 text-center text-sm text-slate-600">B12 Screening Platform v3.0</p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-4 shadow sm:rounded-lg sm:px-10 border border-slate-200">
          {view === "login" ? (
            <form className="space-y-6" onSubmit={handleSubmit}>
              <div>
                <label htmlFor="username" className="block text-sm font-medium text-slate-700">
                  Username
                </label>
                <div className="mt-1 relative rounded-md shadow-sm">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <User className="h-5 w-5 text-slate-400" />
                  </div>
                  <input
                    data-testid="login-username-input"
                    id="username"
                    name="username"
                    type="text"
                    required
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="focus:ring-teal-500 focus:border-teal-500 block w-full pl-10 sm:text-sm border-slate-300 rounded-md py-2.5 border bg-white text-black"
                    placeholder="Enter username"
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between items-center mb-1">
                  <label htmlFor="password" className="block text-sm font-medium text-slate-700">
                    Password
                  </label>
                  <button
                    data-testid="forgot-password-toggle"
                    type="button"
                    className="text-xs font-medium text-teal-600 hover:text-teal-500 focus:outline-none"
                    onClick={toggleView}
                  >
                    Forgot password?
                  </button>
                </div>
                <div className="relative rounded-md shadow-sm">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Lock className="h-5 w-5 text-slate-400" />
                  </div>
                  <input
                    data-testid="login-password-input"
                    id="password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="focus:ring-teal-500 focus:border-teal-500 block w-full pl-10 pr-10 sm:text-sm border-slate-300 rounded-md py-2.5 border bg-white text-black"
                    placeholder="Enter password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute inset-y-0 right-0 pr-3 flex items-center"
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4 text-slate-400 hover:text-slate-600" />
                    ) : (
                      <Eye className="h-4 w-4 text-slate-400 hover:text-slate-600" />
                    )}
                  </button>
                </div>
              </div>

              {error && (
                <div data-testid="login-error" className="text-red-600 text-sm bg-red-50 p-2 rounded border border-red-100 text-center">
                  {error}
                </div>
              )}

              <div>
                <button
                  data-testid="login-submit-button"
                  type="submit"
                  disabled={isLoading}
                  className="w-full flex justify-center py-2.5 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-teal-700 hover:bg-teal-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-teal-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {isLoading ? "Signing in..." : "Sign in"}
                </button>
              </div>
            </form>
          ) : (
            <div className="space-y-6">
              <div className="text-center">
                <h3 className="text-lg font-medium text-slate-900">Account Recovery</h3>
                <p className="mt-1 text-sm text-slate-500">Enter your username or email to reset your password.</p>
              </div>

              {resetStatus === "success" ? (
                <div className="rounded-md bg-green-50 p-4" data-testid="recovery-success">
                  <div className="flex">
                    <div className="flex-shrink-0">
                      <CheckCircle className="h-5 w-5 text-green-400" aria-hidden="true" />
                    </div>
                    <div className="ml-3">
                      <h3 className="text-sm font-medium text-green-800">Recovery email sent</h3>
                      <div className="mt-2 text-sm text-green-700">
                        <p>If an account exists for <b>{username}</b>, you will receive an email shortly.</p>
                      </div>
                      <div className="mt-4">
                        <button
                          data-testid="recovery-return-button"
                          type="button"
                          onClick={toggleView}
                          className="bg-green-50 px-2 py-1.5 rounded-md text-sm font-medium text-green-800 hover:bg-green-100"
                        >
                          Return to Sign In
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleResetSubmit} className="space-y-4">
                  <div>
                    <label htmlFor="recovery-email" className="block text-sm font-medium text-slate-700">
                      Username / Email
                    </label>
                    <div className="mt-1 relative rounded-md shadow-sm">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <Mail className="h-5 w-5 text-slate-400" />
                      </div>
                      <input
                        data-testid="recovery-identifier-input"
                        id="recovery-email"
                        name="recovery-email"
                        type="text"
                        required
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        className="focus:ring-teal-500 focus:border-teal-500 block w-full pl-10 sm:text-sm border-slate-300 rounded-md py-2 border bg-white text-black"
                        placeholder="username or email"
                      />
                    </div>
                  </div>

                  <button
                    data-testid="recovery-submit-button"
                    type="submit"
                    disabled={resetStatus === "loading"}
                    className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-teal-600 hover:bg-teal-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-teal-500 disabled:opacity-50"
                  >
                    {resetStatus === "loading" ? "Sending..." : "Send Recovery Link"}
                  </button>
                </form>
              )}

              {resetStatus !== "success" && (
                <div className="flex items-center justify-center">
                  <button data-testid="recovery-back-button" type="button" onClick={toggleView} className="flex items-center text-sm font-medium text-slate-600 hover:text-teal-600">
                    <ArrowLeft className="h-4 w-4 mr-1" /> Back to Sign In
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Demo Credentials - Clickable */}
          {view === "login" && (
            <div className="mt-6">
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-slate-300" />
                </div>
                <div className="relative flex justify-center text-sm">
                  <span className="px-2 bg-white text-slate-500">Demo Credentials</span>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-3 gap-2" data-testid="demo-credentials">
                <button
                  type="button"
                  onClick={() => fillDemoCredentials("admin_demo", "Demo@2024")}
                  className="bg-purple-50 hover:bg-purple-100 p-2.5 rounded-lg border border-purple-200 transition-colors text-center"
                >
                  <span className="font-semibold text-purple-700 block text-sm">Admin</span>
                  <span className="text-purple-500 text-xs">admin_demo</span>
                </button>
                <button
                  type="button"
                  onClick={() => fillDemoCredentials("lab_demo", "Demo@2024")}
                  className="bg-teal-50 hover:bg-teal-100 p-2.5 rounded-lg border border-teal-200 transition-colors text-center"
                >
                  <span className="font-semibold text-teal-700 block text-sm">Lab Tech</span>
                  <span className="text-teal-500 text-xs">lab_demo</span>
                </button>
                <button
                  type="button"
                  onClick={() => fillDemoCredentials("doctor_demo", "Demo@2024")}
                  className="bg-blue-50 hover:bg-blue-100 p-2.5 rounded-lg border border-blue-200 transition-colors text-center"
                >
                  <span className="font-semibold text-blue-700 block text-sm">Doctor</span>
                  <span className="text-blue-500 text-xs">doctor_demo</span>
                </button>
              </div>
              <p className="text-xs text-slate-400 text-center mt-2">Password: Demo@2024</p>
            </div>
          )}
        </div>

        <div className="mt-4 text-center text-xs text-slate-400">
          <p>HIPAA Compliant • FDA 21 CFR Part 11 Ready</p>
        </div>
      </div>
    </div>
  );
};

export default Login;
