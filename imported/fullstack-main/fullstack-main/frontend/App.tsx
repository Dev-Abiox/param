import React, { useState } from 'react';
import { User, Role } from './types';
import Login from './views/Login';
import Layout from './components/Layout';
import UserWorkspace from './views/UserWorkspace';
import AdminDashboard from './views/AdminDashboard';
import PatientRecords from './views/PatientRecords';
import DoctorList from './views/DoctorList';
import LabList from './views/LabList';
import { AuthService, LisService } from "./services/api";

type ViewType = 'workspace' | 'admin_dashboard' | 'admin_labs' | 'lab_doctors' | 'records';

const App: React.FC = () => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<ViewType>('workspace');
  
  // State for Admin drilling down
  const [selectedLabId, setSelectedLabId] = useState<string | undefined>(undefined);
  const [selectedLabName, setSelectedLabName] = useState<string | undefined>(undefined);
  const [selectedDoctorId, setSelectedDoctorId] = useState<string | undefined>(undefined);
  const [selectedDoctorName, setSelectedDoctorName] = useState<string | undefined>(undefined);

  const handleLogin = async (u: string, p: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const authenticatedUser = await AuthService.login(u, p);
      setUser(authenticatedUser);
      // Default view based on role
      setActiveView(authenticatedUser.role === Role.ADMIN ? 'admin_dashboard' : 'workspace');
    } catch (err) {
      setError('Invalid username or password');
    } finally {
      setIsLoading(false);
    }
  };

  const handleLogout = () => {
    setUser(null);
    setActiveView('workspace');
    resetSelection();
  };

  const resetSelection = () => {
    setSelectedLabId(undefined);
    setSelectedLabName(undefined);
    setSelectedDoctorId(undefined);
    setSelectedDoctorName(undefined);
  }

  // Admin selects a Lab
  const handleSelectLab = (labId: string, labName: string) => {
    setSelectedLabId(labId);
    setSelectedLabName(labName);
    setActiveView('lab_doctors'); // Admin views doctors of that lab
  };

  // Lab or Admin selects a Doctor
  const handleSelectDoctor = (doctorId: string, doctorName: string) => {
    setSelectedDoctorId(doctorId);
    setSelectedDoctorName(doctorName);
    setActiveView('records');
  };

  // Back navigation
  const handleBackToLabs = () => {
    resetSelection();
    setActiveView('admin_labs');
  };

  const handleBackToDoctors = () => {
    setSelectedDoctorId(undefined);
    setSelectedDoctorName(undefined);
    setActiveView('lab_doctors');
  };

  // View Router Logic
  const renderView = () => {
    if (!user) {
      return <Login onLogin={handleLogin} isLoading={isLoading} error={error} />;
    }

    switch (activeView) {
      case 'admin_dashboard':
        if (user.role !== Role.ADMIN) return <div className="p-8 text-red-600">Access Denied</div>;
        return <AdminDashboard />;
      
      case 'admin_labs':
        if (user.role !== Role.ADMIN) return <div className="p-8 text-red-600">Access Denied</div>;
        return <LabList onSelectLab={handleSelectLab} />;

      case 'lab_doctors':
        // If Admin: must have selected a lab.
        // If Lab: shows their own doctors.
        if (user.role === Role.ADMIN) {
           if (!selectedLabId) return <div className="p-8">Please select a Lab first.</div>;
           return (
             <DoctorList 
               labId={selectedLabId} 
               labName={selectedLabName} 
               onSelectDoctor={handleSelectDoctor} 
               onBack={handleBackToLabs}
             />
           );
        } else {
           // Role.LAB
           return (
             <DoctorList 
               onSelectDoctor={handleSelectDoctor} 
               // No back button for Lab user on top level
             />
           );
        }

      case 'records':
        if (user.role === Role.ADMIN) {
           return (
             <PatientRecords 
               doctorId={selectedDoctorId} 
               doctorName={selectedDoctorName}
               onBack={handleBackToDoctors}
             />
           );
        } else {
           // Role.LAB
           // If they came from Doctor list, show back button.
           // If they came from sidebar "Patient Records", they might see all (no doctor filter) or filtered.
           // For simplicity, if a doctor is selected, show back button.
           return (
             <PatientRecords 
               doctorId={selectedDoctorId} 
               doctorName={selectedDoctorName}
               onBack={selectedDoctorId ? handleBackToDoctors : undefined}
             />
           );
        }

      case 'workspace':
      default:
        // Admin cannot see workspace
        if (user.role === Role.ADMIN) return <div className="p-8 text-red-600">Access Denied. Please use Admin Dashboard.</div>;
        return <UserWorkspace />;
    }
  };

  return (
    <Layout 
      user={user} 
      onLogout={handleLogout}
      activeView={activeView}
      onChangeView={(view) => {
        // Reset selection context when navigating via main sidebar
        if (view !== 'records' && view !== 'lab_doctors') {
          resetSelection();
        }
        // Special case: If Lab user clicks "My Doctors", reset specific selection
        if (user?.role === Role.LAB && view === 'lab_doctors') {
            setSelectedDoctorId(undefined);
            setSelectedDoctorName(undefined);
        }
         // Special case: If Lab user clicks "Patient Records", clear filters
        if (user?.role === Role.LAB && view === 'records') {
            setSelectedDoctorId(undefined);
            setSelectedDoctorName(undefined);
        }
        setActiveView(view);
      }}
    >
      {renderView()}
    </Layout>
  );
};

export default App;