export const Role = {
  SUPER_ADMIN: "SUPER_ADMIN",
  LAB: "LAB",
  DOCTOR: "DOCTOR",
  PUBLIC: "PUBLIC",
};

/** True for the platform owner (SUPER_ADMIN role or is_super_admin flag). */
export const isSuperAdmin = (user) =>
  user?.role === Role.SUPER_ADMIN || user?.is_super_admin;

/** True for roles that can manage an organization (users, doctors, billing, usage). */
export const canManageOrg = (role) =>
  role === Role.SUPER_ADMIN || role === Role.LAB;

export const Flag = {
  LOW: "L",
  NORMAL: "N",
  HIGH: "H",
};

// IMPORTANT: matches ZIP UI expectation (1/2/3)
export const ScreeningLabel = {
  NORMAL: 1,
  BORDERLINE: 2,
  DEFICIENT: 3,
};
