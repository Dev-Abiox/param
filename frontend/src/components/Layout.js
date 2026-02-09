import React, { useState } from "react";
import {
  Activity,
  LogOut,
  LayoutDashboard,
  Users,
  FileText,
  Building2,
  Settings,
  Shield,
  Menu,
  X,
  ChevronRight,
  Bell,
  Stethoscope,
  TestTube,
  UserCog,
} from "lucide-react";
import { Role } from "@/types";

// Role-specific configurations
const roleConfig = {
  [Role.ADMIN]: {
    color: "purple",
    bgGradient: "from-purple-600 to-purple-700",
    lightBg: "bg-purple-50",
    textColor: "text-purple-700",
    borderColor: "border-purple-200",
    icon: UserCog,
    title: "Administrator",
    subtitle: "System Management",
  },
  [Role.DOCTOR]: {
    color: "blue",
    bgGradient: "from-blue-600 to-blue-700",
    lightBg: "bg-blue-50",
    textColor: "text-blue-700",
    borderColor: "border-blue-200",
    icon: Stethoscope,
    title: "Physician Portal",
    subtitle: "Patient Care",
  },
  [Role.LAB]: {
    color: "teal",
    bgGradient: "from-teal-600 to-teal-700",
    lightBg: "bg-teal-50",
    textColor: "text-teal-700",
    borderColor: "border-teal-200",
    icon: TestTube,
    title: "Lab Technician",
    subtitle: "Screening & Analysis",
  },
};

const NavItem = ({ icon: Icon, label, active, onClick, badge, roleColor }) => {
  const activeClasses = {
    purple: "bg-purple-50 text-purple-700 border-purple-200",
    blue: "bg-blue-50 text-blue-700 border-blue-200",
    teal: "bg-teal-50 text-teal-700 border-teal-200",
  };

  const iconActiveClasses = {
    purple: "text-purple-600",
    blue: "text-blue-600",
    teal: "text-teal-600",
  };

  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
        active
          ? `${activeClasses[roleColor]} border shadow-sm`
          : "text-slate-600 hover:bg-slate-50 hover:text-slate-800 border border-transparent"
      }`}
    >
      <Icon
        className={`h-5 w-5 ${
          active ? iconActiveClasses[roleColor] : "text-slate-400"
        }`}
      />
      <span className="flex-1 text-left">{label}</span>
      {badge && (
        <span className="px-2 py-0.5 text-xs font-medium bg-amber-100 text-amber-700 rounded-full">
          {badge}
        </span>
      )}
      {active && <ChevronRight className="h-4 w-4 opacity-50" />}
    </button>
  );
};

const Layout = ({ user, onLogout, activeView, onChangeView, children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  if (!user) {
    return <>{children}</>;
  }

  const isAdmin = user.role === Role.ADMIN;
  const isLab = user.role === Role.LAB;
  const isDoctor = user.role === Role.DOCTOR;
  const config = roleConfig[user.role] || roleConfig[Role.LAB];
  const RoleIcon = config.icon;

  const closeSidebar = () => setSidebarOpen(false);

  const handleNavClick = (view) => {
    onChangeView(view);
    closeSidebar();
  };

  const SidebarContent = () => (
    <>
      {/* Logo & Brand */}
      <div className={`p-4 bg-gradient-to-r ${config.bgGradient}`}>
        <div className="flex items-center space-x-3">
          <div className="h-10 w-10 bg-white rounded-xl flex items-center justify-center shadow-sm">
            <img src="/logo.png" alt="Clinomic" className="h-8 w-8 object-contain" />
          </div>
          <div>
            <h1 className="font-bold text-white text-lg">Clinomic</h1>
            <p className="text-xs text-white/80">B12 Screening Platform</p>
          </div>
        </div>
      </div>

      {/* User Info Card */}
      <div className="p-4 border-b border-slate-200">
        <div className={`p-3 rounded-xl ${config.lightBg} ${config.borderColor} border`}>
          <div className="flex items-center space-x-3">
            <div className={`h-12 w-12 bg-gradient-to-br ${config.bgGradient} rounded-xl flex items-center justify-center shadow-sm`}>
              <span className="text-lg font-bold text-white">
                {user.name?.charAt(0) || user.id?.charAt(0) || "U"}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-slate-800 truncate">
                {user.name || user.id}
              </p>
              <div className="flex items-center space-x-1 mt-0.5">
                <RoleIcon className={`h-3.5 w-3.5 ${config.textColor}`} />
                <span className={`text-xs font-medium ${config.textColor}`}>
                  {config.title}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 px-3">
          Main Menu
        </p>

        {isAdmin && (
          <>
            <NavItem
              icon={LayoutDashboard}
              label="Dashboard"
              active={activeView === "admin_dashboard"}
              onClick={() => handleNavClick("admin_dashboard")}
              roleColor={config.color}
            />
            <NavItem
              icon={Building2}
              label="Labs"
              active={activeView === "admin_labs"}
              onClick={() => handleNavClick("admin_labs")}
              roleColor={config.color}
            />
            <NavItem
              icon={Users}
              label="Doctors"
              active={activeView === "lab_doctors"}
              onClick={() => handleNavClick("lab_doctors")}
              roleColor={config.color}
            />
            <NavItem
              icon={FileText}
              label="Records"
              active={activeView === "records"}
              onClick={() => handleNavClick("records")}
              roleColor={config.color}
            />
          </>
        )}

        {isLab && (
          <>
            <NavItem
              icon={Activity}
              label="New Screening"
              active={activeView === "workspace"}
              onClick={() => handleNavClick("workspace")}
              roleColor={config.color}
            />
            <NavItem
              icon={Users}
              label="Doctors"
              active={activeView === "lab_doctors"}
              onClick={() => handleNavClick("lab_doctors")}
              roleColor={config.color}
            />
            <NavItem
              icon={FileText}
              label="Records"
              active={activeView === "records"}
              onClick={() => handleNavClick("records")}
              roleColor={config.color}
            />
          </>
        )}

        {isDoctor && (
          <>
            <NavItem
              icon={LayoutDashboard}
              label="Dashboard"
              active={activeView === "doctor_dashboard"}
              onClick={() => handleNavClick("doctor_dashboard")}
              roleColor={config.color}
            />
            <NavItem
              icon={Activity}
              label="New Screening"
              active={activeView === "workspace"}
              onClick={() => handleNavClick("workspace")}
              roleColor={config.color}
            />
            <NavItem
              icon={FileText}
              label="My Patients"
              active={activeView === "records"}
              onClick={() => handleNavClick("records")}
              roleColor={config.color}
            />
          </>
        )}

        <div className="pt-4 mt-4 border-t border-slate-200">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 px-3">
            Account
          </p>
          <NavItem
            icon={Settings}
            label="Settings"
            active={activeView === "settings"}
            onClick={() => handleNavClick("settings")}
            roleColor={config.color}
          />
        </div>
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-slate-200 bg-slate-50">
        <button
          onClick={onLogout}
          className="w-full flex items-center justify-center space-x-2 px-4 py-2.5 text-sm font-medium text-slate-600 hover:text-red-600 hover:bg-red-50 rounded-lg transition-all duration-200 border border-transparent hover:border-red-200"
        >
          <LogOut className="h-4 w-4" />
          <span>Sign Out</span>
        </button>

        <div className="mt-3 text-center">
          <p className="text-xs text-slate-400">v3.0 • Clinomic Platform</p>
          <div className="flex items-center justify-center space-x-1 mt-1">
            <Shield className="h-3 w-3 text-green-500" />
            <span className="text-xs text-green-600 font-medium">HIPAA Compliant</span>
          </div>
        </div>
      </div>
    </>
  );

  return (
    <div className="flex h-screen bg-slate-100">
      {/* Mobile Overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={closeSidebar}
        />
      )}

      {/* Sidebar - Desktop */}
      <aside className="hidden lg:flex lg:w-72 bg-white border-r border-slate-200 flex-col shadow-sm">
        <SidebarContent />
      </aside>

      {/* Sidebar - Mobile */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-72 bg-white border-r border-slate-200 flex flex-col shadow-xl transform transition-transform duration-300 ease-in-out lg:hidden ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Close button */}
        <button
          onClick={closeSidebar}
          className="absolute top-4 right-4 p-1 rounded-lg hover:bg-slate-100 lg:hidden"
        >
          <X className="h-5 w-5 text-slate-500" />
        </button>
        <SidebarContent />
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Header Bar */}
        <header className="bg-white border-b border-slate-200 px-4 py-3 flex items-center justify-between lg:px-6">
          {/* Mobile Menu Button */}
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 rounded-lg hover:bg-slate-100 lg:hidden"
          >
            <Menu className="h-5 w-5 text-slate-600" />
          </button>

          {/* Page Title - Desktop */}
          <div className="hidden lg:block">
            <h2 className="text-lg font-semibold text-slate-800">
              {activeView === "admin_dashboard" && "Dashboard"}
              {activeView === "doctor_dashboard" && "Dashboard"}
              {activeView === "admin_labs" && "Lab Management"}
              {activeView === "lab_doctors" && "Doctors"}
              {activeView === "workspace" && "B12 Screening"}
              {activeView === "records" && (isDoctor ? "My Patients" : "Patient Records")}
              {activeView === "settings" && "Settings"}
            </h2>
            <p className="text-sm text-slate-500">{config.subtitle}</p>
          </div>

          {/* Mobile Logo */}
          <div className="flex items-center space-x-2 lg:hidden">
            <img src="/logo.png" alt="Clinomic" className="h-8 w-8 object-contain" />
            <span className="font-bold text-slate-800">Clinomic</span>
          </div>

          {/* Right Side Actions */}
          <div className="flex items-center space-x-3">
            <button className="p-2 rounded-lg hover:bg-slate-100 relative">
              <Bell className="h-5 w-5 text-slate-500" />
              <span className="absolute top-1 right-1 h-2 w-2 bg-red-500 rounded-full"></span>
            </button>
            <div className={`hidden sm:flex items-center space-x-2 px-3 py-1.5 rounded-lg ${config.lightBg}`}>
              <div className={`h-8 w-8 bg-gradient-to-br ${config.bgGradient} rounded-lg flex items-center justify-center`}>
                <span className="text-sm font-bold text-white">
                  {user.name?.charAt(0) || "U"}
                </span>
              </div>
              <div className="hidden md:block">
                <p className="text-sm font-medium text-slate-700">{user.name || user.id}</p>
                <p className={`text-xs ${config.textColor}`}>{user.role}</p>
              </div>
            </div>
          </div>
        </header>

        {/* Main Content Area */}
        <main className="flex-1 overflow-y-auto">
          <div className="p-4 lg:p-6">{children}</div>
        </main>
      </div>
    </div>
  );
};

export default Layout;
