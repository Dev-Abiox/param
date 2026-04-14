import { Role } from "@/types";

// URL path → Layout's activeView string. Used by the sidebar to
// highlight the current section after navigation.
export const routeToView = {
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

// Layout's activeView string → URL path. Used by handleChangeView
// when the sidebar triggers a navigation.
export const viewToRoute = {
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

// The landing page each role lands on after login / after a role check
// fails the guard on a route they don't have access to.
export const getDefaultRoute = (role) => {
  switch (role) {
    case Role.SUPER_ADMIN:
      return "/dashboard";
    case Role.LAB:
    case Role.DOCTOR:
    default:
      return "/screening";
  }
};
