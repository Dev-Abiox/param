import React, { useState, useEffect, useCallback, lazy, Suspense } from "react";
import { Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
import "@/App.css";

import { useSessionTimeout } from "@/hooks/useSessionTimeout";

// Eager: needed immediately for unauthenticated users and layout shell
import Login from "@/views/Login";
import Layout from "@/components/Layout";

// Lazy-loaded route views — each becomes a separate chunk
const Signup = lazy(() => import("@/views/Signup"));
const Onboarding = lazy(() => import("@/views/Onboarding"));
const UserWorkspace = lazy(() => import("@/views/UserWorkspace"));
const AdminDashboard = lazy(() => import("@/views/AdminDashboard"));
const PatientRecords = lazy(() => import("@/views/PatientRecords"));
const WorkQueue = lazy(() => import("@/views/WorkQueue"));
const DoctorList = lazy(() => import("@/views/DoctorList"));
const LabList = lazy(() => import("@/views/LabList"));
const Settings = lazy(() => import("@/views/Settings"));
const AdminUsers = lazy(() => import("@/views/admin/AdminUsers"));
const AdminLabs = lazy(() => import("@/views/admin/AdminLabs"));
const AdminDoctors = lazy(() => import("@/views/admin/AdminDoctors"));
const AdminUsage = lazy(() => import("@/views/admin/AdminUsage"));
const AdminBilling = lazy(() => import("@/views/admin/AdminBilling"));
const PlatformDashboard = lazy(() => import("@/views/platform/PlatformDashboard"));
const PlatformOrgList = lazy(() => import("@/views/platform/PlatformOrgList"));
const PlatformCreateOrg = lazy(() => import("@/views/platform/PlatformCreateOrg"));
const PlatformOrgDetail = lazy(() => import("@/views/platform/PlatformOrgDetail"));
const SetPassword = lazy(() => import("@/views/SetPassword"));
const ResetPassword = lazy(() => import("@/views/ResetPassword"));

import { AuthService, BillingService } from "@/services/api";
import MFASetup from "@/components/MFASetup";
import { Role, isSuperAdmin, canManageOrg } from "@/types";
import ErrorBoundary from "@/components/ErrorBoundary";

// Route to view mapping for Layout activeView prop
const routeToView = {
  "/dashboard": "admin_dashboard",
  "/screening": "workspace",
  "/labs": "admin_labs",
  "/doctors": "lab_doctors",
  "/records": "records",
  "/work-queue": "work_queue",
  "/settings": "settings",
  "/portal/users": "admin_users",
  "/portal/labs": "admin_labs_mgmt",
  "/portal/doctors": "admin_doctors_mgmt",
  "/portal/usage": "admin_usage",
  "/portal/billing": "admin_billing",
  "/platform-admin": "platform_dashboard",
  "/platform-admin/orgs": "platform_orgs",
};

// Get default route based on user role
const getDefaultRoute = (role) => {
  switch (role) {
    case Role.SUPER_ADMIN:
      return "/dashboard";
    case Role.LAB:
    case Role.DOCTOR:
    default:
      return "/screening";
  }
};

const App = () => {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();
  const location = useLocation();

  // Selection state for drill-down navigation
  const [selectedLabId, setSelectedLabId] = useState(undefined);
  const [selectedLabName, setSelectedLabName] = useState(undefined);
  const [selectedDoctorId, setSelectedDoctorId] = useState(undefined);
  const [selectedDoctorName, setSelectedDoctorName] = useState(undefined);

  // Track whether onboarding is incomplete (for SUPER_ADMIN / LAB)
  const [onboardingIncomplete, setOnboardingIncomplete] = useState(false);

  // MFA setup required — shown when login returns mfaSetupRequired: true
  const [mfaSetupRequired, setMfaSetupRequired] = useState(false);

  // Check onboarding status for org-managing roles
  const checkOnboarding = async (userData) => {
    if (!canManageOrg(userData.role)) return;
    try {
      const status = await BillingService.getOnboardingStatus();
      if (!status.completed) {
        setOnboardingIncomplete(true);
      } else {
        setOnboardingIncomplete(false);
      }
    } catch {
      // non-critical — don't block login
    }
  };

  // On app load: attempt a silent token refresh using the httpOnly cookie.
  // If the cookie is present and valid, we get a new access token and then
  // fetch the user profile — no localStorage involved.
  useEffect(() => {
    const checkSession = async () => {
      try {
        await AuthService.refresh();
        const userData = await AuthService.getMe();
        // If the session token has mfa_verified=false (restricted token),
        // don't restore the session — force a fresh login which will
        // trigger the proper MFA challenge or setup flow.
        if (userData.mfa_verified === false) {
          await AuthService.logout();
          return;
        }
        setUser(userData);
        await checkOnboarding(userData);
      } catch {
        // Cookie absent or expired — stay on the login screen
      } finally {
        setIsLoading(false);
      }
    };
    checkSession();
  }, []);

  // Listen for the global session-expired event fired by the 401 interceptor
  useEffect(() => {
    const onExpired = () => {
      setUser(null);
      navigate("/login", { replace: true });
    };
    window.addEventListener("session-expired", onExpired);
    return () => window.removeEventListener("session-expired", onExpired);
  }, [navigate]);

  const resetSelection = () => {
    setSelectedLabId(undefined);
    setSelectedLabName(undefined);
    setSelectedDoctorId(undefined);
    setSelectedDoctorName(undefined);
  };

  // loginInProgress tracks the button spinner inside <Login> without
  // toggling the top-level isLoading (which unmounts <Login> and loses
  // MFA challenge state).
  const [loginInProgress, setLoginInProgress] = useState(false);

  const handleLogin = async (u, p) => {
    setLoginInProgress(true);
    setError(null);
    try {
      const result = await AuthService.login(u, p);

      if (result.mfaRequired) {
        setLoginInProgress(false);
        return result;
      }

      // MFA setup required — show MFA setup flow before accessing the app
      if (result.mfaSetupRequired) {
        setUser(result);
        setMfaSetupRequired(true);
        setLoginInProgress(false);
        return result;
      }

      setUser(result);
      // Check onboarding — redirect to wizard if incomplete
      let redirectTo = location.state?.from?.pathname || getDefaultRoute(result.role);
      if (canManageOrg(result.role)) {
        try {
          const obStatus = await BillingService.getOnboardingStatus();
          if (!obStatus.completed) {
            setOnboardingIncomplete(true);
            redirectTo = "/onboarding";
          }
        } catch { /* non-critical */ }
      }
      navigate(redirectTo, { replace: true });
      return result;
    } catch (err) {
      setError(err?.response?.data?.error || "Invalid username or password");
      throw err;
    } finally {
      setLoginInProgress(false);
    }
  };

  const handleMFASuccess = async (authenticatedUser) => {
    // Fetch full user profile (includes lab_code, doctor_code, etc.)
    // MFA verify only returns {id, name, role}.
    let fullUser = authenticatedUser;
    try {
      fullUser = await AuthService.getMe();
    } catch { /* fall back to partial user data */ }
    setUser(fullUser);
    let redirectTo = location.state?.from?.pathname || getDefaultRoute(fullUser.role);
    if (canManageOrg(authenticatedUser.role)) {
      try {
        const obStatus = await BillingService.getOnboardingStatus();
        if (!obStatus.completed) {
          setOnboardingIncomplete(true);
          redirectTo = "/onboarding";
        }
      } catch { /* non-critical */ }
    }
    navigate(redirectTo, { replace: true });
  };

  const handleLogout = useCallback(async () => {
    try {
      await AuthService.logout();
    } finally {
      setUser(null);
      resetSelection();
      navigate("/login", { replace: true });
    }
  }, [navigate]);

  // 15-minute inactivity session timeout (only active when logged in)
  const { showWarning, resetTimer } = useSessionTimeout({
    onTimeout: handleLogout,
    enabled: !!user,
  });

  const handleSelectLab = (labId, labName) => {
    setSelectedLabId(labId);
    setSelectedLabName(labName);
    navigate("/doctors");
  };

  const handleSelectDoctor = (doctorId, doctorName) => {
    setSelectedDoctorId(doctorId);
    setSelectedDoctorName(doctorName);
    navigate("/records");
  };

  const handleBackToLabs = () => {
    resetSelection();
    navigate("/labs");
  };

  const handleBackToDoctors = () => {
    setSelectedDoctorId(undefined);
    setSelectedDoctorName(undefined);
    navigate("/doctors");
  };

  const handleChangeView = (view) => {
    if (view !== "records" && view !== "lab_doctors") {
      resetSelection();
    }
    if (user?.role === Role.LAB && (view === "lab_doctors" || view === "records")) {
      setSelectedDoctorId(undefined);
      setSelectedDoctorName(undefined);
    }

    const viewToRoute = {
      admin_dashboard: "/dashboard",
      workspace: "/screening",
      admin_labs: "/labs",
      lab_doctors: "/doctors",
      records: "/records",
      work_queue: "/work-queue",
      settings: "/settings",
      admin_users: "/portal/users",
      admin_labs_mgmt: "/portal/labs",
      admin_doctors_mgmt: "/portal/doctors",
      admin_usage: "/portal/usage",
      admin_billing: "/portal/billing",
      platform_dashboard: "/platform-admin",
      platform_orgs: "/platform-admin/orgs",
    };

    navigate(viewToRoute[view] || "/");
  };

  const activeView = routeToView[location.pathname] || "workspace";

  // Show loading spinner while checking session
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100 dark:bg-slate-950">
        <div className="text-center">
          <div className="animate-spin h-8 w-8 border-4 border-teal-600 border-t-transparent rounded-full mx-auto mb-4"></div>
          <p className="text-slate-600 dark:text-slate-300">Loading...</p>
        </div>
      </div>
    );
  }

  const routeFallback = (
    <div className="flex items-center justify-center p-8">
      <div className="animate-spin h-6 w-6 border-2 border-teal-600 border-t-transparent rounded-full"></div>
    </div>
  );

  // Not logged in — allow /login and /signup; redirect everything else to /login
  if (!user) {
    return (
      <ErrorBoundary>
      <Suspense fallback={routeFallback}>
      <Routes>
        <Route
          path="/login"
          element={
            <Login
              onLogin={handleLogin}
              onMFARequired={handleMFASuccess}
              isLoading={loginInProgress}
              error={error}
            />
          }
        />
        <Route
          path="/signup"
          element={
            <Signup
              onSignup={(data) => {
                setUser({ id: data.user?.id, name: data.user?.name, role: data.user?.role });
              }}
            />
          }
        />
        <Route path="/set-password/:uid/:token" element={<SetPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
      </Suspense>
      </ErrorBoundary>
    );
  }

  // MFA setup required — block access to the app until MFA is configured
  if (mfaSetupRequired) {
    return (
      <div className="min-h-screen bg-slate-100 dark:bg-slate-950 flex items-center justify-center p-4">
        <div className="w-full max-w-md">
          <MFASetup
            userEmail={user?.email}
            onComplete={async () => {
              // After MFA setup, refresh user data with the new mfa_verified token
              try {
                const userData = await AuthService.getMe();
                setUser(userData);
              } catch { /* user already set */ }
              setMfaSetupRequired(false);
              navigate(getDefaultRoute(user?.role), { replace: true });
            }}
            onCancel={() => {
              // Allow cancel only if MFA is not strictly required (grace period)
              setMfaSetupRequired(false);
              navigate(getDefaultRoute(user?.role), { replace: true });
            }}
          />
        </div>
      </div>
    );
  }

  // Logged in - show app with Layout
  return (
    <ErrorBoundary>
    <Layout
      user={user}
      onLogout={handleLogout}
      activeView={activeView}
      onChangeView={handleChangeView}
    >
      {showWarning && (
        <div className="fixed top-0 inset-x-0 z-50 flex items-center justify-between bg-amber-500 px-4 py-2 text-sm font-medium text-white shadow-md">
          <span>Your session will expire in 1 minute due to inactivity.</span>
          <button
            onClick={resetTimer}
            className="ml-4 rounded bg-white px-3 py-1 text-amber-700 hover:bg-amber-100"
          >
            Stay signed in
          </button>
        </div>
      )}
      <Suspense fallback={routeFallback}>
      <Routes>
        {/* Admin Dashboard (SUPER_ADMIN) */}
        <Route
          path="/dashboard"
          element={
            isSuperAdmin(user) ? (
              <AdminDashboard onboardingIncomplete={onboardingIncomplete} />
            ) : (
              <Navigate to={getDefaultRoute(user.role)} replace />
            )
          }
        />

        {/* Screening Workspace (LAB + DOCTOR/Technician) */}
        <Route
          path="/screening"
          element={
            user.role === Role.LAB || user.role === Role.DOCTOR ? (
              <UserWorkspace user={user} />
            ) : (
              <Navigate to={getDefaultRoute(user.role)} replace />
            )
          }
        />

        {/* Labs List (SUPER_ADMIN + LAB managers can view) */}
        <Route
          path="/labs"
          element={
            canManageOrg(user.role) ? (
              <LabList onSelectLab={handleSelectLab} />
            ) : (
              <Navigate to={getDefaultRoute(user.role)} replace />
            )
          }
        />

        {/* Doctors List (SUPER_ADMIN + LAB) */}
        <Route
          path="/doctors"
          element={
            canManageOrg(user.role) ? (
              isSuperAdmin(user) ? (
                selectedLabId ? (
                  <DoctorList
                    labId={selectedLabId}
                    labName={selectedLabName}
                    onSelectDoctor={handleSelectDoctor}
                    onBack={handleBackToLabs}
                  />
                ) : (
                  <Navigate to="/labs" replace />
                )
              ) : (
                <DoctorList onSelectDoctor={handleSelectDoctor} />
              )
            ) : (
              <Navigate to={getDefaultRoute(user.role)} replace />
            )
          }
        />

        {/* Patient Records (SUPER_ADMIN + DOCTOR + LAB) */}
        <Route
          path="/records"
          element={
            isSuperAdmin(user) ? (
              <PatientRecords
                doctorId={selectedDoctorId}
                doctorName={selectedDoctorName}
                onBack={handleBackToDoctors}
                userRole={user.role}
              />
            ) : user.role === Role.DOCTOR ? (
              <PatientRecords doctorId={user.doctor_code} doctorName={user.name} userRole={user.role} />
            ) : (
              <PatientRecords
                doctorId={selectedDoctorId}
                doctorName={selectedDoctorName}
                onBack={selectedDoctorId ? handleBackToDoctors : undefined}
                userRole={user.role}
              />
            )
          }
        />

        {/* Work Queue (LAB + DOCTOR + SUPER_ADMIN) */}
        <Route
          path="/work-queue"
          element={
            user.role === Role.LAB || user.role === Role.DOCTOR || isSuperAdmin(user) ? (
              <WorkQueue />
            ) : (
              <Navigate to={getDefaultRoute(user.role)} replace />
            )
          }
        />

        {/* Settings */}
        <Route path="/settings" element={<Settings user={user} />} />

        {/* Onboarding wizard (SUPER_ADMIN + LAB owners) */}
        <Route
          path="/onboarding"
          element={canManageOrg(user.role) ? <Onboarding user={user} onComplete={() => setOnboardingIncomplete(false)} /> : <Navigate to={getDefaultRoute(user.role)} replace />}
        />

        {/* Management — Users/Doctors/Usage/Billing (SUPER_ADMIN + LAB) */}
        <Route
          path="/portal/users"
          element={canManageOrg(user.role) ? <AdminUsers user={user} /> : <Navigate to={getDefaultRoute(user.role)} replace />}
        />
        <Route
          path="/portal/labs"
          element={canManageOrg(user.role) ? <AdminLabs /> : <Navigate to={getDefaultRoute(user.role)} replace />}
        />
        <Route
          path="/portal/doctors"
          element={canManageOrg(user.role) ? <AdminDoctors /> : <Navigate to={getDefaultRoute(user.role)} replace />}
        />
        <Route
          path="/portal/usage"
          element={canManageOrg(user.role) ? <AdminUsage /> : <Navigate to={getDefaultRoute(user.role)} replace />}
        />
        <Route
          path="/portal/billing"
          element={canManageOrg(user.role) ? <AdminBilling /> : <Navigate to={getDefaultRoute(user.role)} replace />}
        />

        {/* Platform Super Admin (SUPER_ADMIN only) */}
        <Route
          path="/platform-admin"
          element={
            isSuperAdmin(user) ? (
              <PlatformDashboard />
            ) : (
              <Navigate to={getDefaultRoute(user.role)} replace />
            )
          }
        />
        <Route
          path="/platform-admin/orgs"
          element={
            isSuperAdmin(user) ? (
              <PlatformOrgList />
            ) : (
              <Navigate to={getDefaultRoute(user.role)} replace />
            )
          }
        />
        <Route
          path="/platform-admin/orgs/new"
          element={
            isSuperAdmin(user) ? (
              <PlatformCreateOrg />
            ) : (
              <Navigate to={getDefaultRoute(user.role)} replace />
            )
          }
        />
        <Route
          path="/platform-admin/orgs/:schema"
          element={
            isSuperAdmin(user) ? (
              <PlatformOrgDetail />
            ) : (
              <Navigate to={getDefaultRoute(user.role)} replace />
            )
          }
        />

        {/* Password setup/reset — accessible even when logged in */}
        <Route path="/set-password/:uid/:token" element={<SetPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />

        {/* Default redirect based on role */}
        <Route
          path="/"
          element={<Navigate to={getDefaultRoute(user.role)} replace />}
        />

        {/* Catch all */}
        <Route
          path="*"
          element={<Navigate to={getDefaultRoute(user.role)} replace />}
        />
      </Routes>
      </Suspense>
    </Layout>
    </ErrorBoundary>
  );
};

export default App;
