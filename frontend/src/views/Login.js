import React, { useState, useEffect } from "react";
import { Lock, User, ArrowLeft, Mail, CheckCircle, Shield, Smartphone, Key, Eye, EyeOff, RefreshCw } from "lucide-react";
import { AuthService, MFAService } from "@/services/api";
import ThemeToggle from "@/components/ThemeToggle";

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
  const [mfaMethod, setMfaMethod] = useState("TOTP");
  const [maskedEmail, setMaskedEmail] = useState(null);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [useBackupCode, setUseBackupCode] = useState(false);

  // Resend cooldown timer
  useEffect(() => {
    if (resendCooldown <= 0) return;
    const t = setTimeout(() => setResendCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [resendCooldown]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMfaError(null);

    try {
      const result = await onLogin(username, password);

      // Check if MFA is required
      if (result && result.mfaRequired) {
        setMfaPendingToken(result.mfaPendingToken);
        setPendingUser({ id: result.id, name: result.name, role: result.role });
        setMfaMethod(result.mfaMethod || "TOTP");
        setMaskedEmail(result.maskedEmail || null);
        if (result.mfaMethod === "EMAIL") setResendCooldown(60);
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
      setMfaError(err?.response?.data?.error || err?.response?.data?.detail || "Invalid verification code. Please try again.");
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
    setMfaMethod("TOTP");
    setMaskedEmail(null);
    setResendCooldown(0);
    setUseBackupCode(false);
  };

  const handleResendOTP = async () => {
    setMfaError(null);
    try {
      await MFAService.resendOTP(mfaPendingToken);
      setResendCooldown(60);
    } catch (err) {
      setMfaError(err.response?.data?.error || err.response?.data?.detail || "Failed to resend code. Please try again.");
    }
  };

  const handleResetSubmit = async (e) => {
    e.preventDefault();
    setResetStatus("loading");
    try {
      await AuthService.forgotPassword(username);
    } catch {
      // Always show success to avoid account enumeration
    } finally {
      setResetStatus("success");
    }
  };

  const toggleView = () => {
    setView(view === "login" ? "forgot_password" : "login");
    setResetStatus("idle");
  };

  // MFA Challenge View
  if (view === "mfa_challenge") {
    return (
      <div data-testid="mfa-challenge-page" className="min-h-screen bg-slate-100 dark:bg-slate-950 flex flex-col justify-center py-12 sm:px-6 lg:px-8 relative">
        <div className="absolute top-4 right-4">
          <ThemeToggle />
        </div>
        <div className="sm:mx-auto sm:w-full sm:max-w-md">
          <div className="flex justify-center">
            <div className="h-16 w-16 bg-teal-600 rounded-xl flex items-center justify-center shadow-lg">
              <Shield className="h-10 w-10 text-white" />
            </div>
          </div>
          <h2 className="mt-6 text-center text-2xl font-bold text-slate-900 dark:text-slate-100">Two-Factor Authentication</h2>
          <p className="mt-2 text-center text-sm text-slate-600 dark:text-slate-300">
            Welcome back, <span className="font-medium">{pendingUser?.name || pendingUser?.id}</span>
          </p>
        </div>

        <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
          <div className="bg-white dark:bg-slate-900 py-8 px-4 shadow sm:rounded-lg sm:px-10 border border-slate-200 dark:border-slate-700">
            <div className="mb-6 flex items-center justify-center space-x-2 text-slate-500 dark:text-slate-400">
              {mfaMethod === "EMAIL" ? (
                <>
                  <Mail className="h-5 w-5" />
                  <span className="text-sm">We sent a code to <span className="font-medium">{maskedEmail}</span></span>
                </>
              ) : (
                <>
                  <Smartphone className="h-5 w-5" />
                  <span className="text-sm">Enter the code from your authenticator app</span>
                </>
              )}
            </div>

            <form className="space-y-6" onSubmit={handleMFASubmit}>
              <div>
                <label htmlFor="mfa-code" className="block text-sm font-medium text-slate-700 dark:text-slate-300 text-center mb-2">
                  {useBackupCode ? "Backup Code" : "Verification Code"}
                </label>
                {useBackupCode ? (
                  <input
                    data-testid="mfa-code-input"
                    id="mfa-code"
                    name="mfa-code"
                    type="text"
                    maxLength={20}
                    required
                    autoFocus
                    value={mfaCode}
                    onChange={(e) => setMfaCode(e.target.value)}
                    className="block w-full text-center text-lg tracking-widest font-mono py-3 border-slate-300 dark:border-slate-600 rounded-md focus:ring-teal-500 focus:border-teal-500 border bg-white dark:bg-slate-800 text-black dark:text-white"
                    placeholder="xxxx-xxxx"
                  />
                ) : (
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
                    className="block w-full text-center text-2xl tracking-[0.5em] font-mono py-3 border-slate-300 dark:border-slate-600 rounded-md focus:ring-teal-500 focus:border-teal-500 border bg-white dark:bg-slate-800 text-black dark:text-white"
                    placeholder="000000"
                  />
                )}
              </div>

              {mfaError && (
                <div data-testid="mfa-error" className="text-red-600 text-sm bg-red-50 dark:bg-red-900/30 p-2 rounded border border-red-100 dark:border-red-800 text-center">
                  {mfaError}
                </div>
              )}

              <div>
                <button
                  data-testid="mfa-submit-button"
                  type="submit"
                  disabled={mfaLoading || (useBackupCode ? mfaCode.length < 4 : mfaCode.length !== 6)}
                  className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-teal-700 hover:bg-teal-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-teal-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {mfaLoading ? "Verifying..." : "Verify & Sign In"}
                </button>
              </div>
            </form>

            <div className="mt-6 border-t border-slate-200 dark:border-slate-700 pt-4 space-y-3">
              {mfaMethod === "EMAIL" && (
                <div className="text-center">
                  <button
                    data-testid="mfa-resend-button"
                    type="button"
                    onClick={handleResendOTP}
                    disabled={resendCooldown > 0}
                    className="text-sm text-teal-600 hover:text-teal-700 disabled:text-slate-400 disabled:cursor-not-allowed font-medium"
                  >
                    <RefreshCw className="h-4 w-4 inline mr-1" />
                    {resendCooldown > 0 ? `Resend code (${resendCooldown}s)` : "Resend code"}
                  </button>
                </div>
              )}
              <div className="text-center">
                <button
                  data-testid="use-backup-code-button"
                  type="button"
                  onClick={() => { setUseBackupCode(!useBackupCode); setMfaCode(""); setMfaError(null); }}
                  className="text-sm text-slate-500 dark:text-slate-400 hover:text-teal-600"
                >
                  <Key className="h-4 w-4 inline mr-1" />
                  {useBackupCode ? "Use verification code instead" : "Use a backup code instead"}
                </button>
              </div>
              <div className="flex items-center justify-center">
                <button
                  data-testid="mfa-back-button"
                  type="button"
                  onClick={handleBackToLogin}
                  className="flex items-center text-sm font-medium text-slate-600 dark:text-slate-300 hover:text-teal-600"
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
    <div data-testid="login-page" className="min-h-screen bg-slate-100 dark:bg-slate-950 flex flex-col justify-center py-12 sm:px-6 lg:px-8 relative">
      <div className="absolute top-4 right-4">
        <ThemeToggle />
      </div>
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center">
          <img src="/logo.png?v=17" alt="Clinomic Labs Logo" className="w-auto" style={{ height: '200px' }} />
        </div>
        <h2 className="mt-6 text-center text-3xl font-extrabold text-slate-900 dark:text-slate-100 tracking-tight">Clinomic Labs</h2>
        <p className="mt-2 text-center text-sm text-slate-600 dark:text-slate-300">B12 Screening Platform v3.0</p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white dark:bg-slate-900 py-8 px-4 shadow sm:rounded-lg sm:px-10 border border-slate-200 dark:border-slate-700">
          {view === "login" ? (
            <form className="space-y-6" onSubmit={handleSubmit}>
              <div>
                <label htmlFor="username" className="block text-sm font-medium text-slate-700 dark:text-slate-300">
                  Username
                </label>
                <div className="mt-1 relative rounded-md shadow-sm">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <User className="h-5 w-5 text-slate-400 dark:text-slate-500" />
                  </div>
                  <input
                    data-testid="login-username-input"
                    id="username"
                    name="username"
                    type="text"
                    required
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="focus:ring-teal-500 focus:border-teal-500 block w-full pl-10 sm:text-sm border-slate-300 dark:border-slate-600 rounded-md py-2.5 border bg-white dark:bg-slate-800 text-black dark:text-white"
                    placeholder="Enter username"
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between items-center mb-1">
                  <label htmlFor="password" className="block text-sm font-medium text-slate-700 dark:text-slate-300">
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
                    <Lock className="h-5 w-5 text-slate-400 dark:text-slate-500" />
                  </div>
                  <input
                    data-testid="login-password-input"
                    id="password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="focus:ring-teal-500 focus:border-teal-500 block w-full pl-10 pr-10 sm:text-sm border-slate-300 dark:border-slate-600 rounded-md py-2.5 border bg-white dark:bg-slate-800 text-black dark:text-white"
                    placeholder="Enter password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    className="absolute inset-y-0 right-0 pr-3 flex items-center"
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300" />
                    ) : (
                      <Eye className="h-4 w-4 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300" />
                    )}
                  </button>
                </div>
              </div>

              {error && (
                <div data-testid="login-error" className="text-red-600 text-sm bg-red-50 dark:bg-red-900/30 p-2 rounded border border-red-100 dark:border-red-800 text-center">
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
                <h3 className="text-lg font-medium text-slate-900 dark:text-slate-100">Account Recovery</h3>
                <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Enter your username or email to reset your password.</p>
              </div>

              {resetStatus === "success" ? (
                <div className="rounded-md bg-green-50 dark:bg-green-900/30 p-4" data-testid="recovery-success">
                  <div className="flex">
                    <div className="flex-shrink-0">
                      <CheckCircle className="h-5 w-5 text-green-400" aria-hidden="true" />
                    </div>
                    <div className="ml-3">
                      <h3 className="text-sm font-medium text-green-800 dark:text-green-300">Recovery email sent</h3>
                      <div className="mt-2 text-sm text-green-700 dark:text-green-400">
                        <p>If an account exists for <b>{username}</b>, you will receive an email shortly.</p>
                      </div>
                      <div className="mt-4">
                        <button
                          data-testid="recovery-return-button"
                          type="button"
                          onClick={toggleView}
                          className="bg-green-50 dark:bg-green-900/30 px-2 py-1.5 rounded-md text-sm font-medium text-green-800 dark:text-green-300 hover:bg-green-100 dark:hover:bg-slate-800"
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
                    <label htmlFor="recovery-email" className="block text-sm font-medium text-slate-700 dark:text-slate-300">
                      Username / Email
                    </label>
                    <div className="mt-1 relative rounded-md shadow-sm">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <Mail className="h-5 w-5 text-slate-400 dark:text-slate-500" />
                      </div>
                      <input
                        data-testid="recovery-identifier-input"
                        id="recovery-email"
                        name="recovery-email"
                        type="text"
                        required
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        className="focus:ring-teal-500 focus:border-teal-500 block w-full pl-10 sm:text-sm border-slate-300 dark:border-slate-600 rounded-md py-2 border bg-white dark:bg-slate-800 text-black dark:text-white"
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
                  <button data-testid="recovery-back-button" type="button" onClick={toggleView} className="flex items-center text-sm font-medium text-slate-600 dark:text-slate-300 hover:text-teal-600">
                    <ArrowLeft className="h-4 w-4 mr-1" /> Back to Sign In
                  </button>
                </div>
              )}
            </div>
          )}

        </div>

        <div className="mt-4 text-center text-xs text-slate-400 dark:text-slate-500">
          <p>HIPAA Compliant • FDA 21 CFR Part 11 Ready</p>
        </div>
      </div>
    </div>
  );
};

export default Login;
