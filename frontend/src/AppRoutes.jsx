import React, { lazy } from "react";
import { Routes, Route, Navigate } from "react-router-dom";

import { Role, isSuperAdmin, canManageOrg } from "@/types";
import { getDefaultRoute } from "@/lib/routing";
import Protected from "@/components/Protected";

// Lazy-loaded route views — each becomes a separate chunk.
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

/**
 * AppRoutes — the authenticated app's route table.
 *
 * Pulled out of App.js so the top-level component stays focused on
 * session restore + auth handlers, and so each lazy-loaded view
 * ships with its own Sentry.ErrorBoundary via <Protected> (a render
 * error in /records no longer takes down the whole app).
 */
const AppRoutes = ({
  user,
  selectedLabId,
  selectedLabName,
  selectedDoctorId,
  selectedDoctorName,
  handleSelectLab,
  handleSelectDoctor,
  handleBackToLabs,
  handleBackToDoctors,
  navigate,
}) => {
  const defaultRoute = getDefaultRoute(user.role);

  return (
    <Routes>
      {/* Admin Dashboard (SUPER_ADMIN) */}
      <Route
        path="/dashboard"
        element={
          <Protected allowed={isSuperAdmin(user)} role={user.role}>
            <AdminDashboard />
          </Protected>
        }
      />

      {/* Screening Workspace (LAB + DOCTOR/Technician) */}
      <Route
        path="/screening"
        element={
          <Protected
            allowed={user.role === Role.LAB || user.role === Role.DOCTOR}
            role={user.role}
          >
            <UserWorkspace user={user} />
          </Protected>
        }
      />

      {/* Labs List (SUPER_ADMIN + LAB managers can view) */}
      <Route
        path="/labs"
        element={
          <Protected allowed={canManageOrg(user.role)} role={user.role}>
            <LabList onSelectLab={handleSelectLab} />
          </Protected>
        }
      />

      {/* Doctors List (SUPER_ADMIN + LAB) */}
      <Route
        path="/doctors"
        element={
          <Protected allowed={canManageOrg(user.role)} role={user.role}>
            {isSuperAdmin(user) ? (
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
            )}
          </Protected>
        }
      />

      {/* Patient Records (SUPER_ADMIN + DOCTOR + LAB) */}
      <Route
        path="/records"
        element={
          <Protected allowed={true} role={user.role}>
            {isSuperAdmin(user) ? (
              <PatientRecords
                doctorId={selectedDoctorId}
                doctorName={selectedDoctorName}
                onBack={handleBackToDoctors}
                userRole={user.role}
              />
            ) : user.role === Role.DOCTOR ? (
              <PatientRecords doctorName={user.name} userRole={user.role} />
            ) : (
              <PatientRecords
                doctorId={selectedDoctorId}
                doctorName={selectedDoctorName}
                onBack={selectedDoctorId ? handleBackToDoctors : undefined}
                userRole={user.role}
              />
            )}
          </Protected>
        }
      />

      {/* Work Queue (LAB + SUPER_ADMIN) */}
      <Route
        path="/work-queue"
        element={
          <Protected
            allowed={user.role === Role.LAB || isSuperAdmin(user)}
            role={user.role}
          >
            <WorkQueue />
          </Protected>
        }
      />

      {/* Settings */}
      <Route
        path="/settings"
        element={
          <Protected allowed={true} role={user.role}>
            <Settings user={user} />
          </Protected>
        }
      />

      {/* Onboarding wizard (LAB owners only) */}
      <Route
        path="/onboarding"
        element={
          <Protected allowed={user.role === Role.LAB} role={user.role}>
            <Onboarding user={user} />
          </Protected>
        }
      />

      {/* Management — Users/Labs/Doctors/Usage/Billing (SUPER_ADMIN + LAB) */}
      <Route
        path="/portal/users"
        element={
          <Protected allowed={canManageOrg(user.role)} role={user.role}>
            <AdminUsers user={user} />
          </Protected>
        }
      />
      <Route
        path="/portal/labs"
        element={
          <Protected allowed={canManageOrg(user.role)} role={user.role}>
            <AdminLabs />
          </Protected>
        }
      />
      <Route
        path="/portal/doctors"
        element={
          <Protected allowed={canManageOrg(user.role)} role={user.role}>
            <AdminDoctors />
          </Protected>
        }
      />
      <Route
        path="/portal/usage"
        element={
          <Protected allowed={canManageOrg(user.role)} role={user.role}>
            <AdminUsage />
          </Protected>
        }
      />
      <Route
        path="/portal/billing"
        element={
          <Protected allowed={canManageOrg(user.role)} role={user.role}>
            <AdminBilling />
          </Protected>
        }
      />

      {/* Platform Super Admin (SUPER_ADMIN only) */}
      <Route
        path="/platform-admin"
        element={
          <Protected allowed={isSuperAdmin(user)} role={user.role}>
            <PlatformDashboard />
          </Protected>
        }
      />
      <Route
        path="/platform-admin/orgs"
        element={
          <Protected allowed={isSuperAdmin(user)} role={user.role}>
            <PlatformOrgList />
          </Protected>
        }
      />
      <Route
        path="/platform-admin/orgs/new"
        element={
          <Protected allowed={isSuperAdmin(user)} role={user.role}>
            <PlatformCreateOrg />
          </Protected>
        }
      />
      <Route
        path="/platform-admin/orgs/:schema"
        element={
          <Protected allowed={isSuperAdmin(user)} role={user.role}>
            <PlatformOrgDetail />
          </Protected>
        }
      />

      {/* Default redirect based on role */}
      <Route path="/" element={<Navigate to={defaultRoute} replace />} />

      {/* Catch-all */}
      <Route path="*" element={<Navigate to={defaultRoute} replace />} />
    </Routes>
  );
};

export default AppRoutes;
