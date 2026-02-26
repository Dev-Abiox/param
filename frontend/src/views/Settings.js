import React, { useState, useEffect, useCallback } from "react";
import { User, Shield, Key, Bell, Lock, CheckCircle, AlertTriangle, Smartphone, Monitor, RefreshCw, Server, Database, Activity } from "lucide-react";
import MFASetup from "@/components/MFASetup";
import { MFAService, AdminService, AuthService } from "@/services/api";
import { Role } from "@/types";

const Settings = ({ user }) => {
  const [activeTab, setActiveTab] = useState("security");
  const [mfaStatus, setMfaStatus] = useState(null);
  const [systemHealth, setSystemHealth] = useState(null);
  const [showMFASetup, setShowMFASetup] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [sessions, setSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [revokingId, setRevokingId] = useState(null);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const status = await MFAService.getStatus();
      setMfaStatus(status);

      if (user.role === Role.SUPER_ADMIN) {
        const health = await AdminService.getSystemHealth();
        setSystemHealth(health);
      }
    } catch (err) {
      console.error("Failed to load settings data:", err);
    } finally {
      setIsLoading(false);
    }
  }, [user.role]);

  const loadSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const data = await AuthService.getSessions();
      setSessions(data);
    } catch (err) {
      console.error("Failed to load sessions:", err);
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  const handleRevokeSession = async (tokenId) => {
    setRevokingId(tokenId);
    try {
      await AuthService.revokeSession(tokenId);
      setSessions((prev) => prev.filter((s) => s.id !== tokenId));
    } catch (err) {
      console.error("Failed to revoke session:", err);
    } finally {
      setRevokingId(null);
    }
  };

  useEffect(() => {
    loadData();
    loadSessions();
  }, [loadData, loadSessions]);

  const tabs = [
    { id: "security", label: "Security", icon: Shield },
    { id: "account", label: "Account", icon: User },
    ...(user.role === Role.SUPER_ADMIN ? [{ id: "system", label: "System", icon: Server }] : []),
  ];

  const renderSecurityTab = () => (
    <div className="space-y-6">
      {/* MFA Section */}
      <div className="bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
        <div className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <Smartphone className="h-5 w-5 text-teal-600" />
              <h3 className="font-semibold text-slate-800 dark:text-slate-100">Two-Factor Authentication</h3>
            </div>
            {mfaStatus?.is_enabled ? (
              <span className="px-2 py-1 text-xs font-medium bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded-full flex items-center">
                <CheckCircle className="h-3 w-3 mr-1" /> Enabled
              </span>
            ) : (
              <span className="px-2 py-1 text-xs font-medium bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 rounded-full flex items-center">
                <AlertTriangle className="h-3 w-3 mr-1" /> Not Enabled
              </span>
            )}
          </div>
        </div>

        <div className="p-4">
          {showMFASetup ? (
            <MFASetup
              userEmail={`${user.id}@clinomic.local`}
              onComplete={() => {
                setShowMFASetup(false);
                loadData();
              }}
              onCancel={() => setShowMFASetup(false)}
            />
          ) : (
            <div>
              <p className="text-sm text-slate-600 dark:text-slate-300 mb-4">
                Add an extra layer of security to your account by enabling two-factor authentication.
              </p>

              {mfaStatus?.is_enabled ? (
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                    <div>
                      <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
                        Method: {mfaStatus?.mfa_method === 'EMAIL' ? 'Email Code' : 'Authenticator App'}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        Backup codes remaining: {mfaStatus?.backup_codes_remaining || 0}
                      </p>
                    </div>
                    <span className="text-lg font-bold text-teal-600">{mfaStatus?.backup_codes_remaining || 0}</span>
                  </div>
                  <div className="flex space-x-3">
                    <button
                      onClick={() => setShowMFASetup(true)}
                      className="px-4 py-2 border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 rounded-md text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800"
                    >
                      Manage MFA
                    </button>
                  </div>
                </div>
              ) : (
                <div>
                  {mfaStatus?.mfa_required_for_role && (
                    <div className="mb-4 p-3 bg-amber-50 dark:bg-amber-900/30 border border-amber-100 dark:border-amber-800 rounded-lg text-sm text-amber-700 dark:text-amber-400 flex items-start">
                      <AlertTriangle className="h-5 w-5 mr-2 mt-0.5" />
                      <div>
                        <p className="font-medium">MFA Required</p>
                        <p>Your role ({user.role}) requires two-factor authentication for enhanced security.</p>
                      </div>
                    </div>
                  )}
                  <button
                    onClick={() => setShowMFASetup(true)}
                    className="px-4 py-2 bg-teal-600 text-white rounded-md text-sm font-medium hover:bg-teal-700 flex items-center"
                  >
                    <Shield className="h-4 w-4 mr-2" /> Enable Two-Factor Auth
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Active Sessions */}
      <div className="bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
        <div className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <Monitor className="h-5 w-5 text-teal-600" />
              <h3 className="font-semibold text-slate-800 dark:text-slate-100">Active Sessions</h3>
            </div>
            <button onClick={loadSessions} aria-label="Refresh sessions" className="text-slate-400 dark:text-slate-500 hover:text-teal-600">
              <RefreshCw className={`h-4 w-4 ${sessionsLoading ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>
        <div className="p-4 space-y-2">
          {sessionsLoading ? (
            <div className="text-center py-4 text-slate-400 dark:text-slate-500 text-sm">
              <RefreshCw className="h-5 w-5 animate-spin mx-auto mb-1" /> Loading sessions...
            </div>
          ) : sessions.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400 text-center py-4">No active sessions found.</p>
          ) : (
            sessions.map((session, idx) => (
              <div key={session.id} className="flex items-center justify-between p-3 border border-slate-200 dark:border-slate-700 rounded-lg">
                <div className="flex items-center space-x-3">
                  <div className="h-9 w-9 bg-slate-100 dark:bg-slate-800 rounded-full flex items-center justify-center">
                    <Monitor className="h-4 w-4 text-slate-500 dark:text-slate-400" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
                      {idx === 0 ? "Current session" : `Session ${idx + 1}`}
                    </p>
                    <p className="text-xs text-slate-400 dark:text-slate-500">
                      Last active: {session.last_used_at
                        ? new Date(session.last_used_at).toLocaleString()
                        : new Date(session.created_at).toLocaleString()}
                    </p>
                  </div>
                </div>
                {idx === 0 ? (
                  <span className="px-2 py-1 text-xs font-medium bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded-full">Current</span>
                ) : (
                  <button
                    onClick={() => handleRevokeSession(session.id)}
                    disabled={revokingId === session.id}
                    className="px-3 py-1 text-xs font-medium text-red-600 border border-red-200 dark:border-red-800 rounded hover:bg-red-50 disabled:opacity-50"
                  >
                    {revokingId === session.id ? "Revoking..." : "Revoke"}
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Password */}
      <div className="bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
        <div className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 px-4 py-3">
          <div className="flex items-center space-x-3">
            <Key className="h-5 w-5 text-teal-600" />
            <h3 className="font-semibold text-slate-800 dark:text-slate-100">Password</h3>
          </div>
        </div>
        <div className="p-4">
          <p className="text-sm text-slate-600 dark:text-slate-300 mb-4">
            It's recommended to use a strong, unique password and change it periodically.
          </p>
          <button className="px-4 py-2 border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 rounded-md text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800">
            Change Password
          </button>
        </div>
      </div>
    </div>
  );

  const renderAccountTab = () => (
    <div className="space-y-6">
      <div className="bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
        <div className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 px-4 py-3">
          <h3 className="font-semibold text-slate-800 dark:text-slate-100">Profile Information</h3>
        </div>
        <div className="p-4 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">Username</label>
              <p className="text-sm text-slate-800 dark:text-slate-100 font-medium">{user.id}</p>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">Display Name</label>
              <p className="text-sm text-slate-800 dark:text-slate-100 font-medium">{user.name}</p>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">Role</label>
              <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                user.role === Role.SUPER_ADMIN ? "bg-purple-100 text-purple-700" :
                user.role === Role.DOCTOR ? "bg-blue-100 text-blue-700" :
                "bg-teal-100 text-teal-700"
              }`}>
                {user.role}
              </span>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">Organization</label>
              <p className="text-sm text-slate-800 dark:text-slate-100 font-medium">Clinomic Labs</p>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
        <div className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 px-4 py-3">
          <div className="flex items-center space-x-3">
            <Bell className="h-5 w-5 text-teal-600" />
            <h3 className="font-semibold text-slate-800 dark:text-slate-100">Notifications</h3>
          </div>
        </div>
        <div className="p-4 space-y-3">
          {[
            { label: "Email notifications for critical alerts", enabled: true },
            { label: "Daily summary reports", enabled: false },
            { label: "Security alerts", enabled: true },
          ].map((item, index) => (
            <div key={index} className="flex items-center justify-between py-2">
              <span className="text-sm text-slate-600 dark:text-slate-300">{item.label}</span>
              <button
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  item.enabled ? "bg-teal-600" : "bg-slate-200 dark:bg-slate-700"
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    item.enabled ? "translate-x-6" : "translate-x-1"
                  }`}
                />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );

  const renderSystemTab = () => (
    <div className="space-y-6">
      {/* System Health */}
      <div className="bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
        <div className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <Activity className="h-5 w-5 text-teal-600" />
              <h3 className="font-semibold text-slate-800 dark:text-slate-100">System Health</h3>
            </div>
            <button
              onClick={loadData}
              aria-label="Refresh system health"
              className="text-slate-400 dark:text-slate-500 hover:text-teal-600"
            >
              <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>
        <div className="p-4">
          {systemHealth ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                <div className="flex items-center space-x-3">
                  <div className={`h-3 w-3 rounded-full ${
                    systemHealth.status === "healthy" ? "bg-green-500" : "bg-amber-500"
                  }`} />
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-300">Overall Status</span>
                </div>
                <span className={`text-sm font-medium ${
                  systemHealth.status === "healthy" ? "text-green-600" : "text-amber-600"
                }`}>
                  {systemHealth.status?.toUpperCase()}
                </span>
              </div>

              {systemHealth.components && Object.entries(systemHealth.components).map(([key, value]) => (
                <div key={key} className="flex items-center justify-between p-3 border border-slate-200 dark:border-slate-700 rounded-lg">
                  <div className="flex items-center space-x-3">
                    {key === "database" && <Database className="h-4 w-4 text-slate-400 dark:text-slate-500" />}
                    {key === "model_engine" && <Activity className="h-4 w-4 text-slate-400 dark:text-slate-500" />}
                    {key === "crypto" && <Lock className="h-4 w-4 text-slate-400 dark:text-slate-500" />}
                    {key === "audit" && <Shield className="h-4 w-4 text-slate-400 dark:text-slate-500" />}
                    <span className="text-sm text-slate-600 dark:text-slate-300 capitalize">{key.replace("_", " ")}</span>
                  </div>
                  <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                    value.status === "healthy" ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400" : "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400"
                  }`}>
                    {value.status}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-4 text-slate-500 dark:text-slate-400">
              <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2" />
              Loading system health...
            </div>
          )}
        </div>
      </div>

      {/* Audit Status */}
      {systemHealth?.components?.audit && (
        <div className="bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
          <div className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 px-4 py-3">
            <div className="flex items-center space-x-3">
              <Shield className="h-5 w-5 text-teal-600" />
              <h3 className="font-semibold text-slate-800 dark:text-slate-100">Audit Log Integrity</h3>
            </div>
          </div>
          <div className="p-4">
            <div className="grid grid-cols-3 gap-4">
              <div className="text-center p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                <p className="text-2xl font-bold text-teal-600">{systemHealth.components.audit.entries || 0}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400">Total Entries</p>
              </div>
              <div className="text-center p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                <p className={`text-2xl font-bold ${
                  systemHealth.components.audit.integrity?.verified ? "text-green-600" : "text-amber-600"
                }`}>
                  {systemHealth.components.audit.integrity?.verified ? "✓" : "!"}
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">Chain Verified</p>
              </div>
              <div className="text-center p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                <p className="text-2xl font-bold text-slate-600 dark:text-slate-300">
                  {systemHealth.components.audit.integrity?.issues || 0}
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">Issues Found</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="max-w-4xl mx-auto" data-testid="settings-page">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Settings</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">Manage your account and security preferences</p>
      </div>

      {/* Tabs */}
      <div className="bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 mb-6">
        <div className="flex border-b border-slate-200 dark:border-slate-700">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center space-x-2 px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? "border-teal-600 text-teal-600"
                  : "border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
              }`}
            >
              <tab.icon className="h-4 w-4" />
              <span>{tab.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === "security" && renderSecurityTab()}
      {activeTab === "account" && renderAccountTab()}
      {activeTab === "system" && (user.role === Role.SUPER_ADMIN) && renderSystemTab()}
    </div>
  );
};

export default Settings;
