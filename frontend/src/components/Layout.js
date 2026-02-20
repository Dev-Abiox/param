import React, { useState, useEffect, useRef } from "react";
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
  BarChart2,
  CreditCard,
} from "lucide-react";
import { Role } from "@/types";
import { NotificationService } from "@/services/api";
import ThemeToggle from "@/components/ThemeToggle";

// Role-specific configurations
const roleConfig = {
  [Role.ADMIN]: {
    color: "purple",
    bgGradient: "from-purple-600 to-purple-700",
    lightBg: "bg-purple-50 dark:bg-purple-900/30",
    textColor: "text-purple-700 dark:text-purple-400",
    borderColor: "border-purple-200 dark:border-purple-700",
    icon: UserCog,
    title: "Administrator",
    subtitle: "System Management",
  },
  [Role.DOCTOR]: {
    color: "blue",
    bgGradient: "from-blue-600 to-blue-700",
    lightBg: "bg-blue-50 dark:bg-blue-900/30",
    textColor: "text-blue-700 dark:text-blue-400",
    borderColor: "border-blue-200 dark:border-blue-700",
    icon: Stethoscope,
    title: "Physician Portal",
    subtitle: "Patient Care",
  },
  [Role.LAB]: {
    color: "teal",
    bgGradient: "from-teal-600 to-teal-700",
    lightBg: "bg-teal-50 dark:bg-teal-900/30",
    textColor: "text-teal-700 dark:text-teal-400",
    borderColor: "border-teal-200 dark:border-teal-700",
    icon: TestTube,
    title: "Lab Technician",
    subtitle: "Screening & Analysis",
  },
};

const NavItem = ({ icon: Icon, label, active, onClick, badge, roleColor }) => {
  const activeClasses = {
    purple: "bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400 border-purple-200 dark:border-purple-700",
    blue: "bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-700",
    teal: "bg-teal-50 dark:bg-teal-900/30 text-teal-700 dark:text-teal-400 border-teal-200 dark:border-teal-700",
  };

  const iconActiveClasses = {
    purple: "text-purple-600 dark:text-purple-400",
    blue: "text-blue-600 dark:text-blue-400",
    teal: "text-teal-600 dark:text-teal-400",
  };

  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${active
        ? `${activeClasses[roleColor]} border shadow-sm`
        : "text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 hover:text-slate-800 dark:hover:text-slate-200 border border-transparent"
        }`}
    >
      <Icon
        className={`h-5 w-5 ${active ? iconActiveClasses[roleColor] : "text-slate-400 dark:text-slate-500"
          }`}
      />
      <span className="flex-1 text-left">{label}</span>
      {badge && (
        <span className="px-2 py-0.5 text-xs font-medium bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 rounded-full">
          {badge}
        </span>
      )}
      {active && <ChevronRight className="h-4 w-4 opacity-50" />}
    </button>
  );
};

const Layout = ({ user, onLogout, activeView, onChangeView, children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifOpen, setNotifOpen] = useState(false);
  const notifRef = useRef(null);

  // Load notifications on mount and every 60 seconds
  useEffect(() => {
    if (!user) return;
    const load = async () => {
      try {
        const data = await NotificationService.getAll();
        setNotifications(data.notifications || []);
        setUnreadCount(data.unread_count ?? 0);
      } catch {
        // silent — notifications are non-critical
      }
    };
    load();
    const interval = setInterval(load, 60000);
    return () => clearInterval(interval);
  }, [user]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClick = (e) => {
      if (notifRef.current && !notifRef.current.contains(e.target)) {
        setNotifOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const handleMarkRead = async (id) => {
    try {
      await NotificationService.markRead(id);
      setNotifications((prev) => prev.map((n) => n.id === id ? { ...n, is_read: true } : n));
      setUnreadCount((c) => Math.max(0, c - 1));
    } catch {
      // silent
    }
  };

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
          <div className="h-16 w-16 rounded-xl flex items-center justify-center">
            <img src="/clean-logo.png?v=1" alt="Clinomic" className="h-full w-full object-contain p-0" />
          </div>
          <div>
            <h1 className="font-bold text-white text-lg">Clinomic</h1>
            <p className="text-xs text-white/80">B12 Screening Platform</p>
          </div>
        </div>
      </div>

      {/* User Info Card */}
      <div className="p-4 border-b border-slate-200 dark:border-slate-700">
        <div className={`p-3 rounded-xl ${config.lightBg} ${config.borderColor} border`}>
          <div className="flex items-center space-x-3">
            <div className={`h-12 w-12 bg-gradient-to-br ${config.bgGradient} rounded-xl flex items-center justify-center shadow-sm`}>
              <span className="text-lg font-bold text-white">
                {user.name?.charAt(0) || user.id?.charAt(0) || "U"}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">
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
        <p className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-3 px-3">
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
              icon={FileText}
              label="Work Queue"
              active={activeView === "work_queue"}
              onClick={() => handleNavClick("work_queue")}
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

        {isAdmin && (
          <div className="pt-4 mt-4 border-t border-slate-200 dark:border-slate-700">
            <p className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-3 px-3">
              Management
            </p>
            <NavItem
              icon={Users}
              label="Users"
              active={activeView === "admin_users"}
              onClick={() => handleNavClick("admin_users")}
              roleColor={config.color}
            />
            <NavItem
              icon={Building2}
              label="Labs"
              active={activeView === "admin_labs_mgmt"}
              onClick={() => handleNavClick("admin_labs_mgmt")}
              roleColor={config.color}
            />
            <NavItem
              icon={Stethoscope}
              label="Doctors"
              active={activeView === "admin_doctors_mgmt"}
              onClick={() => handleNavClick("admin_doctors_mgmt")}
              roleColor={config.color}
            />
            <NavItem
              icon={BarChart2}
              label="Usage"
              active={activeView === "admin_usage"}
              onClick={() => handleNavClick("admin_usage")}
              roleColor={config.color}
            />
            <NavItem
              icon={CreditCard}
              label="Billing"
              active={activeView === "admin_billing"}
              onClick={() => handleNavClick("admin_billing")}
              roleColor={config.color}
            />
          </div>
        )}

        <div className="pt-4 mt-4 border-t border-slate-200 dark:border-slate-700">
          <p className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-3 px-3">
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
      <div className="p-4 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800">
        <button
          onClick={onLogout}
          className="w-full flex items-center justify-center space-x-2 px-4 py-2.5 text-sm font-medium text-slate-600 dark:text-slate-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg transition-all duration-200 border border-transparent hover:border-red-200 dark:hover:border-red-800"
        >
          <LogOut className="h-4 w-4" />
          <span>Sign Out</span>
        </button>

        <div className="mt-3 text-center">
          <p className="text-xs text-slate-400 dark:text-slate-500">v3.0 • Clinomic Platform</p>
          <div className="flex items-center justify-center space-x-1 mt-1">
            <Shield className="h-3 w-3 text-green-500" />
            <span className="text-xs text-green-600 dark:text-green-400 font-medium">HIPAA Compliant</span>
          </div>
        </div>
      </div>
    </>
  );

  return (
    <div className="flex h-screen bg-slate-100 dark:bg-slate-950">
      {/* Mobile Overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={closeSidebar}
        />
      )}

      {/* Sidebar - Desktop */}
      <aside className="hidden lg:flex lg:w-72 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-700 flex-col shadow-sm">
        <SidebarContent />
      </aside>

      {/* Sidebar - Mobile */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-72 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-700 flex flex-col shadow-xl transform transition-transform duration-300 ease-in-out lg:hidden ${sidebarOpen ? "translate-x-0" : "-translate-x-full"
          }`}
      >
        {/* Close button */}
        <button
          onClick={closeSidebar}
          className="absolute top-4 right-4 p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 lg:hidden"
        >
          <X className="h-5 w-5 text-slate-500 dark:text-slate-400" />
        </button>
        <SidebarContent />
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Header Bar */}
        <header className="bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-700 px-4 py-3 flex items-center justify-between lg:px-6">
          {/* Mobile Menu Button */}
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 lg:hidden"
          >
            <Menu className="h-5 w-5 text-slate-600 dark:text-slate-400" />
          </button>

          {/* Page Title - Desktop */}
          <div className="hidden lg:block">
            <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">
              {activeView === "admin_dashboard" && "Dashboard"}
              {activeView === "doctor_dashboard" && "Dashboard"}
              {activeView === "admin_labs" && "Lab Management"}
              {activeView === "lab_doctors" && "Doctors"}
              {activeView === "workspace" && "B12 Screening"}
              {activeView === "work_queue" && "Work Queue"}
              {activeView === "records" && (isDoctor ? "My Patients" : "Patient Records")}
              {activeView === "settings" && "Settings"}
              {activeView === "admin_users" && "Users"}
              {activeView === "admin_labs_mgmt" && "Labs Management"}
              {activeView === "admin_doctors_mgmt" && "Doctors Management"}
              {activeView === "admin_usage" && "Usage"}
              {activeView === "admin_billing" && "Billing"}
            </h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">{config.subtitle}</p>
          </div>

          {/* Mobile Logo */}
          <div className="flex items-center space-x-2 lg:hidden">
            <img src="/clean-logo.png?v=1" alt="Clinomic" className="h-8 w-8 object-contain" />
            <span className="font-bold text-slate-800 dark:text-slate-100">Clinomic</span>
          </div>

          {/* Right Side Actions */}
          <div className="flex items-center space-x-3">
            <ThemeToggle />
            {/* Notification Bell */}
            <div className="relative" ref={notifRef}>
              <button
                onClick={() => setNotifOpen((o) => !o)}
                className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 relative"
              >
                <Bell className="h-5 w-5 text-slate-500 dark:text-slate-400" />
                {unreadCount > 0 && (
                  <span className="absolute top-0.5 right-0.5 h-4 w-4 flex items-center justify-center text-[10px] font-bold bg-red-500 text-white rounded-full">
                    {unreadCount > 9 ? "9+" : unreadCount}
                  </span>
                )}
              </button>

              {notifOpen && (
                <div className="absolute right-0 mt-2 w-80 bg-white dark:bg-slate-900 rounded-xl shadow-lg border border-slate-200 dark:border-slate-700 z-50 overflow-hidden">
                  <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-700 flex items-center justify-between">
                    <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">Notifications</span>
                    {unreadCount > 0 && (
                      <span className="text-xs font-medium text-slate-500 dark:text-slate-400">{unreadCount} unread</span>
                    )}
                  </div>
                  <ul className="max-h-80 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-700">
                    {notifications.length === 0 ? (
                      <li className="px-4 py-6 text-center text-sm text-slate-400 dark:text-slate-500">
                        No notifications
                      </li>
                    ) : (
                      notifications.map((n) => (
                        <li
                          key={n.id}
                          className={`px-4 py-3 flex flex-col gap-0.5 ${n.is_read ? "opacity-60" : "bg-blue-50/40 dark:bg-blue-900/20"}`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <span className="text-sm font-medium text-slate-800 dark:text-slate-100 leading-snug">
                              {n.title}
                            </span>
                            {!n.is_read && (
                              <button
                                onClick={() => handleMarkRead(n.id)}
                                className="shrink-0 text-xs text-blue-600 dark:text-blue-400 hover:underline mt-0.5"
                              >
                                Mark read
                              </button>
                            )}
                          </div>
                          <p className="text-xs text-slate-500 dark:text-slate-400 leading-snug">{n.body}</p>
                          <span className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">
                            {new Date(n.created_at).toLocaleString()}
                          </span>
                        </li>
                      ))
                    )}
                  </ul>
                </div>
              )}
            </div>
            <div className={`hidden sm:flex items-center space-x-2 px-3 py-1.5 rounded-lg ${config.lightBg}`}>
              <div className={`h-8 w-8 bg-gradient-to-br ${config.bgGradient} rounded-lg flex items-center justify-center`}>
                <span className="text-sm font-bold text-white">
                  {user.name?.charAt(0) || "U"}
                </span>
              </div>
              <div className="hidden md:block">
                <p className="text-sm font-medium text-slate-700 dark:text-slate-300">{user.name || user.id}</p>
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
