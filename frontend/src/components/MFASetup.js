import React, { useState, useEffect, useCallback } from "react";
import { Shield, Smartphone, Key, CheckCircle, Copy, AlertTriangle, RefreshCw, Mail } from "lucide-react";
import { MFAService } from "@/services/api";

const MFASetup = ({ userEmail, onComplete, onCancel }) => {
  const [step, setStep] = useState("loading"); // loading, status, choose_method, setup, email_verify, backup_codes, complete
  const [mfaStatus, setMfaStatus] = useState(null);
  const [setupData, setSetupData] = useState(null);
  const [selectedMethod, setSelectedMethod] = useState(null);
  const [verificationCode, setVerificationCode] = useState("");
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [copiedCode, setCopiedCode] = useState(null);
  const [resendCooldown, setResendCooldown] = useState(0);

  useEffect(() => {
    loadMFAStatus();
  }, []);

  // Resend cooldown timer
  useEffect(() => {
    if (resendCooldown <= 0) return;
    const t = setTimeout(() => setResendCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [resendCooldown]);

  const loadMFAStatus = async () => {
    try {
      const status = await MFAService.getStatus();
      setMfaStatus(status);
      setStep("status");
    } catch (err) {
      setError("Failed to load MFA status");
      setStep("status");
    }
  };

  const handleChooseMethod = () => {
    setError(null);
    setStep("choose_method");
  };

  const handleStartSetup = async (method) => {
    setIsLoading(true);
    setError(null);
    setSelectedMethod(method);
    try {
      const data = await MFAService.setup(userEmail, method);
      setSetupData(data);
      if (method === "EMAIL") {
        setResendCooldown(60);
        setStep("email_verify");
      } else {
        setStep("setup");
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.response?.data?.error || "Failed to initialize MFA setup");
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerify = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    try {
      const result = await MFAService.verifySetup(verificationCode);
      setSetupData((prev) => ({ ...prev, backup_codes: result.backup_codes }));
      setStep("backup_codes");
    } catch (err) {
      setError(err.response?.data?.detail || "Invalid verification code");
    } finally {
      setIsLoading(false);
    }
  };

  const handleResendOTP = async () => {
    setError(null);
    try {
      await MFAService.setup(userEmail, "EMAIL");
      setResendCooldown(60);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to resend code");
    }
  };

  const handleDisable = async () => {
    const code = prompt("Enter your current MFA code to disable:");
    if (!code) return;

    setIsLoading(true);
    setError(null);
    try {
      await MFAService.disable(code);
      await loadMFAStatus();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to disable MFA");
    } finally {
      setIsLoading(false);
    }
  };

  const copyToClipboard = (text, index) => {
    navigator.clipboard.writeText(text);
    setCopiedCode(index);
    setTimeout(() => setCopiedCode(null), 2000);
  };

  const copyAllCodes = () => {
    const allCodes = setupData?.backup_codes?.join("\n") || "";
    navigator.clipboard.writeText(allCodes);
    setCopiedCode("all");
    setTimeout(() => setCopiedCode(null), 2000);
  };

  // Method label helper
  const methodLabel = mfaStatus?.mfa_method === "EMAIL" ? "Email Code" : "Authenticator App";

  // Status View
  if (step === "status") {
    return (
      <div className="bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-6">
        <div className="flex items-center space-x-3 mb-6">
          <div className="h-10 w-10 bg-teal-100 rounded-lg flex items-center justify-center">
            <Shield className="h-6 w-6 text-teal-600" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Two-Factor Authentication</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">Add an extra layer of security to your account</p>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-100 dark:border-red-800 rounded text-sm text-red-600 dark:text-red-400">
            {error}
          </div>
        )}

        {mfaStatus?.is_enabled ? (
          <div>
            <div className="flex items-center p-4 bg-green-50 dark:bg-green-900/30 border border-green-100 dark:border-green-800 rounded-lg mb-4">
              <CheckCircle className="h-5 w-5 text-green-500 mr-3" />
              <div>
                <p className="font-medium text-green-800 dark:text-green-300">MFA is enabled</p>
                <p className="text-sm text-green-600">
                  Method: {methodLabel} &middot; Backup codes remaining: {mfaStatus.backup_codes_remaining}
                </p>
              </div>
            </div>

            <div className="flex space-x-3">
              <button
                onClick={handleDisable}
                disabled={isLoading}
                className="px-4 py-2 border border-red-300 text-red-600 dark:text-red-400 rounded-md text-sm font-medium hover:bg-red-50 disabled:opacity-50"
              >
                Disable MFA
              </button>
              <button
                onClick={onCancel}
                className="px-4 py-2 border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 rounded-md text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800"
              >
                Close
              </button>
            </div>
          </div>
        ) : (
          <div>
            <div className="flex items-center p-4 bg-amber-50 dark:bg-amber-900/30 border border-amber-100 dark:border-amber-800 rounded-lg mb-4">
              <AlertTriangle className="h-5 w-5 text-amber-500 mr-3" />
              <div>
                <p className="font-medium text-amber-800 dark:text-amber-300">MFA is not enabled</p>
                <p className="text-sm text-amber-600">
                  {mfaStatus?.mfa_required_for_role
                    ? "MFA is required for your role. Please set it up now."
                    : "Enable MFA for enhanced account security."}
                </p>
              </div>
            </div>

            <div className="flex space-x-3">
              <button
                onClick={handleChooseMethod}
                disabled={isLoading}
                className="px-4 py-2 bg-teal-600 text-white rounded-md text-sm font-medium hover:bg-teal-700 disabled:opacity-50 flex items-center"
              >
                {isLoading ? (
                  <><RefreshCw className="h-4 w-4 mr-2 animate-spin" /> Setting up...</>
                ) : (
                  <><Shield className="h-4 w-4 mr-2" /> Enable MFA</>
                )}
              </button>
              {!mfaStatus?.mfa_required_for_role && (
                <button
                  onClick={onCancel}
                  className="px-4 py-2 border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 rounded-md text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800"
                >
                  Skip for now
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    );
  }

  // Choose Method View
  if (step === "choose_method") {
    return (
      <div className="bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-6">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-2">Choose Verification Method</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">Select how you'd like to verify your identity</p>

        {error && (
          <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-100 dark:border-red-800 rounded text-sm text-red-600 dark:text-red-400">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
          <button
            onClick={() => handleStartSetup("TOTP")}
            disabled={isLoading}
            className="flex flex-col items-center p-6 border-2 border-slate-200 dark:border-slate-700 rounded-lg hover:border-teal-500 dark:hover:border-teal-500 transition-colors text-left disabled:opacity-50"
          >
            <Smartphone className="h-10 w-10 text-teal-600 mb-3" />
            <span className="font-semibold text-slate-900 dark:text-slate-100 mb-1">Authenticator App</span>
            <span className="text-xs text-slate-500 dark:text-slate-400 text-center">
              Use Google Authenticator, Authy, or similar app
            </span>
          </button>

          <button
            onClick={() => handleStartSetup("EMAIL")}
            disabled={isLoading}
            className="flex flex-col items-center p-6 border-2 border-slate-200 dark:border-slate-700 rounded-lg hover:border-teal-500 dark:hover:border-teal-500 transition-colors text-left disabled:opacity-50"
          >
            <Mail className="h-10 w-10 text-teal-600 mb-3" />
            <span className="font-semibold text-slate-900 dark:text-slate-100 mb-1">Email Code</span>
            <span className="text-xs text-slate-500 dark:text-slate-400 text-center">
              Receive a verification code at your email
            </span>
          </button>
        </div>

        {isLoading && (
          <div className="flex items-center justify-center text-sm text-slate-500">
            <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> Setting up...
          </div>
        )}

        <button
          onClick={() => setStep("status")}
          className="w-full px-4 py-2 border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 rounded-md text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800"
        >
          Back
        </button>
      </div>
    );
  }

  // TOTP Setup View - Show QR Code
  if (step === "setup") {
    return (
      <div className="bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-6">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-2">Set Up Authenticator App</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">Scan the QR code with your authenticator app (Google Authenticator, Authy, etc.)</p>

        {error && (
          <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-100 dark:border-red-800 rounded text-sm text-red-600 dark:text-red-400">
            {error}
          </div>
        )}

        <div className="flex flex-col items-center mb-6">
          <div className="bg-white dark:bg-slate-900 p-4 border-2 border-slate-200 dark:border-slate-700 rounded-lg mb-4">
            {setupData?.qr_code ? (
              <img
                src={setupData.qr_code}
                alt="MFA QR Code"
                className="w-48 h-48"
              />
            ) : (
              <div className="w-48 h-48 bg-slate-100 dark:bg-slate-800 flex items-center justify-center">
                <Smartphone className="h-12 w-12 text-slate-300 dark:text-slate-600" />
              </div>
            )}
          </div>

          <div className="text-center">
            <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">Can't scan? Enter this code manually:</p>
            <code className="text-sm bg-slate-100 dark:bg-slate-800 px-3 py-1 rounded font-mono">
              {setupData?.otpauth_url?.split("secret=")[1]?.split("&")[0] || "Loading..."}
            </code>
          </div>
        </div>

        <form onSubmit={handleVerify} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Enter the 6-digit code from your app
            </label>
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              maxLength={6}
              value={verificationCode}
              onChange={(e) => setVerificationCode(e.target.value.replace(/\D/g, ""))}
              className="w-full text-center text-xl tracking-[0.5em] font-mono py-3 border border-slate-300 dark:border-slate-600 rounded-md bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:ring-teal-500 focus:border-teal-500"
              placeholder="000000"
              autoFocus
            />
          </div>

          <div className="flex space-x-3">
            <button
              type="submit"
              disabled={isLoading || verificationCode.length !== 6}
              className="flex-1 px-4 py-2 bg-teal-600 text-white rounded-md text-sm font-medium hover:bg-teal-700 disabled:opacity-50"
            >
              {isLoading ? "Verifying..." : "Verify & Enable"}
            </button>
            <button
              type="button"
              onClick={() => { setVerificationCode(""); setStep("choose_method"); }}
              className="px-4 py-2 border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 rounded-md text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800"
            >
              Back
            </button>
          </div>
        </form>
      </div>
    );
  }

  // Email OTP Verify View
  if (step === "email_verify") {
    return (
      <div className="bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-6">
        <div className="flex items-center space-x-3 mb-4">
          <div className="h-10 w-10 bg-teal-100 rounded-lg flex items-center justify-center">
            <Mail className="h-6 w-6 text-teal-600" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Verify Your Email</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              We sent a 6-digit code to <span className="font-medium">{setupData?.email_masked || userEmail}</span>
            </p>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-100 dark:border-red-800 rounded text-sm text-red-600 dark:text-red-400">
            {error}
          </div>
        )}

        <form onSubmit={handleVerify} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Enter the 6-digit code from your email
            </label>
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              maxLength={6}
              value={verificationCode}
              onChange={(e) => setVerificationCode(e.target.value.replace(/\D/g, ""))}
              className="w-full text-center text-xl tracking-[0.5em] font-mono py-3 border border-slate-300 dark:border-slate-600 rounded-md bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:ring-teal-500 focus:border-teal-500"
              placeholder="000000"
              autoFocus
            />
          </div>

          <div className="flex space-x-3">
            <button
              type="submit"
              disabled={isLoading || verificationCode.length !== 6}
              className="flex-1 px-4 py-2 bg-teal-600 text-white rounded-md text-sm font-medium hover:bg-teal-700 disabled:opacity-50"
            >
              {isLoading ? "Verifying..." : "Verify & Enable"}
            </button>
            <button
              type="button"
              onClick={handleResendOTP}
              disabled={resendCooldown > 0}
              className="px-4 py-2 border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 rounded-md text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
            >
              {resendCooldown > 0 ? `Resend (${resendCooldown}s)` : "Resend Code"}
            </button>
          </div>

          <button
            type="button"
            onClick={() => { setVerificationCode(""); setStep("choose_method"); }}
            className="w-full px-4 py-2 border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 rounded-md text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800"
          >
            Back
          </button>
        </form>
      </div>
    );
  }

  // Backup Codes View
  if (step === "backup_codes") {
    return (
      <div className="bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-6">
        <div className="flex items-center space-x-3 mb-4">
          <CheckCircle className="h-8 w-8 text-green-500" />
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">MFA Enabled Successfully!</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">Save your backup codes in a secure location</p>
          </div>
        </div>

        <div className="bg-amber-50 dark:bg-amber-900/30 border border-amber-100 dark:border-amber-800 rounded-lg p-4 mb-4">
          <div className="flex items-start">
            <AlertTriangle className="h-5 w-5 text-amber-500 mr-2 mt-0.5" />
            <div className="text-sm text-amber-800 dark:text-amber-300">
              <p className="font-medium">Important: Save these backup codes</p>
              <p className="mt-1">Each code can only be used once. Store them securely - you won't see them again.</p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 mb-4">
          {setupData?.backup_codes?.map((code, index) => (
            <div
              key={index}
              className="flex items-center justify-between bg-slate-50 dark:bg-slate-800 px-3 py-2 rounded border border-slate-200 dark:border-slate-700 font-mono text-sm"
            >
              <span>{code}</span>
              <button
                onClick={() => copyToClipboard(code, index)}
                className="text-slate-400 dark:text-slate-500 hover:text-teal-600 dark:hover:text-teal-400"
              >
                {copiedCode === index ? (
                  <CheckCircle className="h-4 w-4 text-green-500" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
              </button>
            </div>
          ))}
        </div>

        <div className="flex space-x-3">
          <button
            onClick={copyAllCodes}
            className="flex-1 px-4 py-2 border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 rounded-md text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800 flex items-center justify-center"
          >
            {copiedCode === "all" ? (
              <><CheckCircle className="h-4 w-4 mr-2 text-green-500" /> Copied!</>
            ) : (
              <><Copy className="h-4 w-4 mr-2" /> Copy All Codes</>
            )}
          </button>
          <button
            onClick={() => {
              if (onComplete) onComplete();
              setStep("complete");
            }}
            className="flex-1 px-4 py-2 bg-teal-600 text-white rounded-md text-sm font-medium hover:bg-teal-700"
          >
            I've Saved My Codes
          </button>
        </div>
      </div>
    );
  }

  // Complete View
  if (step === "complete") {
    return (
      <div className="bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-6 text-center">
        <div className="flex justify-center mb-4">
          <div className="h-16 w-16 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center">
            <CheckCircle className="h-10 w-10 text-green-500" />
          </div>
        </div>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-2">All Set!</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
          Your account is now protected with two-factor authentication.
        </p>
        <button
          onClick={onCancel}
          className="px-6 py-2 bg-teal-600 text-white rounded-md text-sm font-medium hover:bg-teal-700"
        >
          Continue to Dashboard
        </button>
      </div>
    );
  }

  // Loading
  return (
    <div className="bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-6 text-center">
      <RefreshCw className="h-8 w-8 text-teal-600 animate-spin mx-auto mb-4" />
      <p className="text-slate-500 dark:text-slate-400">Loading MFA settings...</p>
    </div>
  );
};

export default MFASetup;
