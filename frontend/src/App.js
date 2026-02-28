import React, { useState, useEffect, lazy, Suspense } from "react";
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

import { AuthService } from "@/services/api";
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

  // On app load: attempt a silent token refresh using the httpOnly cookie.
  // If the cookie is present and valid, we get a new access token and then
  // fetch the user profile — no localStorage involved.
  useEffect(() => {
    const checkSession = async () => {
      try {
        await AuthService.refresh();
        const userData = await AuthService.getMe();
        setUser(userData);
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

  const handleLogin = async (u, p) => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await AuthService.login(u, p);

      if (result.mfaRequired) {
        setIsLoading(false);
        return result;
      }

      setUser(result);
      const from = location.state?.from?.pathname;
      const defaultRoute = getDefaultRoute(result.role);
      navigate(from || defaultRoute, { replace: true });
      return result;
    } catch (err) {
      setError("Invalid username or password");
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const handleMFASuccess = (authenticatedUser) => {
    setUser(authenticatedUser);
    const from = location.state?.from?.pathname;
    const defaultRoute = getDefaultRoute(authenticatedUser.role);
    navigate(from || defaultRoute, { replace: true });
  };

  const handleLogout = async () => {
    try {
      await AuthService.logout();
    } finally {
      setUser(null);
      resetSelection();
      navigate("/login", { replace: true });
    }
  };

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
              isLoading={isLoading}
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
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
      </Suspense>
      </ErrorBoundary>
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
              <AdminDashboard />
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
                  <div className="p-8 text-center">
                    <p className="text-slate-600 mb-4">Please select a Lab first.</p>
                    <button
                      onClick={() => navigate("/labs")}
                      className="px-4 py-2 bg-teal-600 text-white rounded hover:bg-teal-700"
                    >
                      Go to Labs
                    </button>
                  </div>
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
          element={canManageOrg(user.role) ? <Onboarding user={user} /> : <Navigate to={getDefaultRoute(user.role)} replace />}
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
