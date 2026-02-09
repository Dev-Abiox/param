import React, { useState, useEffect } from "react";
import { Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
import "@/App.css";

import Login from "@/views/Login";
import Layout from "@/components/Layout";
import UserWorkspace from "@/views/UserWorkspace";
import AdminDashboard from "@/views/AdminDashboard";
import DoctorDashboard from "@/views/DoctorDashboard";
import PatientRecords from "@/views/PatientRecords";
import DoctorList from "@/views/DoctorList";
import LabList from "@/views/LabList";
import Settings from "@/views/Settings";

import { AuthService } from "@/services/api";
import { Role } from "@/types";

// Route to view mapping for Layout activeView prop
const routeToView = {
  "/dashboard": "admin_dashboard",
  "/doctor-dashboard": "doctor_dashboard",
  "/screening": "workspace",
  "/labs": "admin_labs",
  "/doctors": "lab_doctors",
  "/records": "records",
  "/settings": "settings",
};

// Get default route based on user role
const getDefaultRoute = (role) => {
  switch (role) {
    case Role.ADMIN:
      return "/dashboard";
    case Role.DOCTOR:
      return "/doctor-dashboard";
    case Role.LAB:
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

  // Check for existing session on app load
  useEffect(() => {
    const checkSession = async () => {
      const token = localStorage.getItem("access_token");
      if (token) {
        try {
          const userData = await AuthService.getMe();
          setUser(userData);
        } catch (err) {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
        }
      }
      setIsLoading(false);
    };
    checkSession();
  }, []);

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

  const handleLogout = () => {
    AuthService.logout();
    setUser(null);
    resetSelection();
    navigate("/login", { replace: true });
  };

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
      doctor_dashboard: "/doctor-dashboard",
      workspace: "/screening",
      admin_labs: "/labs",
      lab_doctors: "/doctors",
      records: "/records",
      settings: "/settings",
    };

    navigate(viewToRoute[view] || "/");
  };

  const activeView = routeToView[location.pathname] || "workspace";

  // Show loading spinner while checking session
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100">
        <div className="text-center">
          <div className="animate-spin h-8 w-8 border-4 border-teal-600 border-t-transparent rounded-full mx-auto mb-4"></div>
          <p className="text-slate-600">Loading...</p>
        </div>
      </div>
    );
  }

  // Not logged in - show login or redirect to login
  if (!user) {
    return (
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
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  // Logged in - show app with Layout
  return (
    <Layout
      user={user}
      onLogout={handleLogout}
      activeView={activeView}
      onChangeView={handleChangeView}
    >
      <Routes>
        {/* Admin Dashboard */}
        <Route
          path="/dashboard"
          element={
            user.role === Role.ADMIN ? (
              <AdminDashboard />
            ) : (
              <Navigate to={getDefaultRoute(user.role)} replace />
            )
          }
        />

        {/* Doctor Dashboard */}
        <Route
          path="/doctor-dashboard"
          element={
            user.role === Role.DOCTOR ? (
              <DoctorDashboard user={user} />
            ) : (
              <Navigate to={getDefaultRoute(user.role)} replace />
            )
          }
        />

        {/* Screening Workspace */}
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

        {/* Labs List (Admin only) */}
        <Route
          path="/labs"
          element={
            user.role === Role.ADMIN ? (
              <LabList onSelectLab={handleSelectLab} />
            ) : (
              <Navigate to={getDefaultRoute(user.role)} replace />
            )
          }
        />

        {/* Doctors List */}
        <Route
          path="/doctors"
          element={
            user.role === Role.ADMIN || user.role === Role.LAB ? (
              user.role === Role.ADMIN ? (
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

        {/* Patient Records */}
        <Route
          path="/records"
          element={
            user.role === Role.ADMIN ? (
              <PatientRecords
                doctorId={selectedDoctorId}
                doctorName={selectedDoctorName}
                onBack={handleBackToDoctors}
              />
            ) : user.role === Role.DOCTOR ? (
              <PatientRecords doctorId={user.doctor_code} doctorName={user.name} />
            ) : (
              <PatientRecords
                doctorId={selectedDoctorId}
                doctorName={selectedDoctorName}
                onBack={selectedDoctorId ? handleBackToDoctors : undefined}
              />
            )
          }
        />

        {/* Settings */}
        <Route path="/settings" element={<Settings user={user} />} />

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
    </Layout>
  );
};

export default App;
