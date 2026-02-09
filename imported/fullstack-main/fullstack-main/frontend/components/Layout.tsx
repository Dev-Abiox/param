import React from 'react';
import { User, Role } from '../types';
import { LogOut, Activity, LayoutDashboard, Database, Settings, FlaskConical, Stethoscope, Users } from 'lucide-react';

type ViewType = 'workspace' | 'admin_dashboard' | 'admin_labs' | 'lab_doctors' | 'records';

interface LayoutProps {
  children: React.ReactNode;
  user: User | null;
  onLogout: () => void;
  activeView: ViewType;
  onChangeView: (view: ViewType) => void;
}

const Layout: React.FC<LayoutProps> = ({ children, user, onLogout, activeView, onChangeView }) => {
  if (!user) return <>{children}</>;

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden font-sans text-slate-900">
      {/* Sidebar - LIS Style: Dark, dense, professional */}
      <aside className="w-64 bg-slate-850 text-white flex flex-col shadow-xl z-20">
        <div className="h-16 flex items-center px-6 border-b border-slate-700 bg-slate-900">
          <Activity className="w-6 h-6 text-teal-400 mr-3" />
          <div>
            <h1 className="font-bold text-lg tracking-tight">Clinomic Labs</h1>
            <p className="text-[10px] text-slate-400 uppercase tracking-wider">v2.5.0 Enterprise</p>
          </div>
        </div>

        <nav className="flex-1 py-6 px-3 space-y-1">
          {/* ADMIN MENU */}
          {user.role === Role.ADMIN && (
            <>
              <button
                onClick={() => onChangeView('admin_dashboard')}
                className={`w-full flex items-center px-4 py-3 text-sm font-medium rounded-md transition-colors ${
                  activeView === 'admin_dashboard'
                    ? 'bg-teal-600 text-white shadow-sm'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`}
              >
                <LayoutDashboard className="w-5 h-5 mr-3" />
                Admin Dashboard
              </button>

              <button
                onClick={() => onChangeView('admin_labs')}
                className={`w-full flex items-center px-4 py-3 text-sm font-medium rounded-md transition-colors ${
                  activeView === 'admin_labs' || activeView === 'lab_doctors' || activeView === 'records'
                    ? 'bg-teal-600 text-white shadow-sm'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`}
              >
                <FlaskConical className="w-5 h-5 mr-3" />
                Lab Registry
              </button>
            </>
          )}

          {/* LAB MENU */}
          {user.role === Role.LAB && (
            <>
              <button
                onClick={() => onChangeView('workspace')}
                className={`w-full flex items-center px-4 py-3 text-sm font-medium rounded-md transition-colors ${
                  activeView === 'workspace'
                    ? 'bg-teal-600 text-white shadow-sm'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`}
              >
                <Activity className="w-5 h-5 mr-3" />
                Screening Workspace
              </button>
              
               <button 
                onClick={() => onChangeView('lab_doctors')}
                className={`w-full flex items-center px-4 py-3 text-sm font-medium rounded-md transition-colors ${
                  activeView === 'lab_doctors'
                    ? 'bg-teal-600 text-white shadow-sm'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`}
              >
                <Stethoscope className="w-5 h-5 mr-3" />
                My Doctors
              </button>

              <button 
                onClick={() => onChangeView('records')}
                className={`w-full flex items-center px-4 py-3 text-sm font-medium rounded-md transition-colors ${
                  activeView === 'records'
                    ? 'bg-teal-600 text-white shadow-sm'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`}
              >
                <Database className="w-5 h-5 mr-3" />
                Patient Records
              </button>
            </>
          )}

           <div className="pt-4 mt-4 border-t border-slate-700">
            <button className="w-full flex items-center px-4 py-3 text-sm font-medium text-slate-300 rounded-md hover:bg-slate-800 hover:text-white transition-colors">
              <Settings className="w-5 h-5 mr-3" />
              System Config
            </button>
          </div>
        </nav>

        <div className="p-4 border-t border-slate-700 bg-slate-900">
          <div className="flex items-center">
            <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center text-xs font-bold text-white border border-slate-600">
              {user.name.charAt(0)}
            </div>
            <div className="ml-3">
              <p className="text-sm font-medium text-white max-w-[120px] truncate">{user.name}</p>
              <p className="text-xs text-slate-400 capitalize">{user.role === 'LAB' ? 'Pathology Lab' : 'Admin'}</p>
            </div>
            <button 
              onClick={onLogout}
              className="ml-auto p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-full transition-colors"
              title="Logout"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col overflow-hidden relative">
        {/* Top Status Bar (Hospital Info) */}
        <header className="h-10 bg-white border-b border-slate-200 flex items-center justify-between px-6 shadow-sm z-10">
          <div className="flex items-center space-x-6 text-xs font-medium text-slate-500">
            <span>Server: US-East-2a</span>
            <span className="h-4 w-px bg-slate-300"></span>
            <span>Gateway: 192.168.1.104</span>
            <span className="h-4 w-px bg-slate-300"></span>
            <span className="text-teal-600 flex items-center">
              <span className="w-2 h-2 rounded-full bg-teal-500 mr-2 animate-pulse"></span>
              Secure Connection Active
            </span>
          </div>
          <div className="text-xs text-slate-400 font-mono">
            {new Date().toLocaleDateString()} {new Date().toLocaleTimeString()}
          </div>
        </header>

        <div className="flex-1 overflow-auto bg-slate-100 p-6 custom-scrollbar">
          {children}
        </div>
      </main>
    </div>
  );
};

export default Layout;