import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Users, AlertTriangle, TrendingUp, Activity, FileText, Calendar, CheckCircle2 } from "lucide-react";
import { LisService } from "../services/api";

const DoctorDashboard = ({ user }) => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchStats = async () => {
      try {
        // Fetch doctor-specific stats
        const data = await LisService.getStats(user?.id);
        setStats(data);
      } catch (e) {
        console.error("Failed to load stats", e);
        // Set default stats if API fails
        setStats({
          totalPatients: 0,
          screeningsToday: 0,
          deficientCases: 0,
          recentPatients: []
        });
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, [user?.id]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-96 text-slate-400" data-testid="doctor-dashboard-loading">
        <Activity className="w-8 h-8 animate-spin mb-4 text-blue-600" />
        <p>Loading dashboard...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="doctor-dashboard">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Welcome, Dr. {user?.name || "Doctor"}</h2>
          <p className="text-sm text-slate-500">Your patient overview and recent activity</p>
        </div>
        <div className="flex items-center px-4 py-2 bg-blue-50 text-blue-700 rounded-lg border border-blue-200">
          <Calendar className="w-4 h-4 mr-2" />
          <span className="text-sm font-medium">{new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</span>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm flex items-center justify-between" data-testid="stat-total-patients">
          <div>
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wide">Total Patients</p>
            <h3 className="text-3xl font-extrabold text-slate-800 mt-1">{stats?.totalPatients || stats?.totalCases || 0}</h3>
            <p className="text-xs text-slate-500 mt-1">All time records</p>
          </div>
          <div className="p-3 rounded-full bg-blue-50 text-blue-600 border border-blue-100">
            <Users className="w-6 h-6" />
          </div>
        </div>

        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm flex items-center justify-between" data-testid="stat-screenings-today">
          <div>
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wide">Screenings Today</p>
            <h3 className="text-3xl font-extrabold text-slate-800 mt-1">{stats?.screeningsToday || stats?.dailyTests || 0}</h3>
            <p className="text-xs text-green-600 font-medium mt-1 flex items-center">
              <TrendingUp className="w-3 h-3 mr-1" /> Active
            </p>
          </div>
          <div className="p-3 rounded-full bg-green-50 text-green-600 border border-green-100">
            <Activity className="w-6 h-6" />
          </div>
        </div>

        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm flex items-center justify-between" data-testid="stat-deficient">
          <div>
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wide">Deficient Cases</p>
            <h3 className="text-3xl font-extrabold text-slate-800 mt-1">{stats?.deficientCases || stats?.distribution?.[2]?.value || 0}</h3>
            <p className="text-xs text-red-500 font-medium mt-1">Requires attention</p>
          </div>
          <div className="p-3 rounded-full bg-red-50 text-red-600 border border-red-100">
            <AlertTriangle className="w-6 h-6" />
          </div>
        </div>

        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm flex items-center justify-between" data-testid="stat-normal">
          <div>
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wide">Normal Results</p>
            <h3 className="text-3xl font-extrabold text-slate-800 mt-1">{stats?.normalCases || stats?.distribution?.[0]?.value || 0}</h3>
            <p className="text-xs text-green-600 font-medium mt-1 flex items-center">
              <CheckCircle2 className="w-3 h-3 mr-1" /> Healthy
            </p>
          </div>
          <div className="p-3 rounded-full bg-emerald-50 text-emerald-600 border border-emerald-100">
            <CheckCircle2 className="w-6 h-6" />
          </div>
        </div>
      </div>

      {/* Quick Actions - Centered */}
      <div className="flex justify-center gap-6">
        <button
          onClick={() => navigate("/screening")}
          className="bg-gradient-to-br from-blue-500 to-blue-600 p-6 rounded-lg shadow-sm text-white hover:from-blue-600 hover:to-blue-700 transition-all hover:shadow-md cursor-pointer text-left w-72"
        >
          <Activity className="w-8 h-8 mb-3 opacity-80" />
          <h4 className="font-bold text-lg">New Screening</h4>
          <p className="text-sm text-blue-100 mt-1">Start a new B12 deficiency screening for your patient</p>
        </button>
        <button
          onClick={() => navigate("/records")}
          className="bg-gradient-to-br from-slate-700 to-slate-800 p-6 rounded-lg shadow-sm text-white hover:from-slate-800 hover:to-slate-900 transition-all hover:shadow-md cursor-pointer text-left w-72"
        >
          <FileText className="w-8 h-8 mb-3 opacity-80" />
          <h4 className="font-bold text-lg">View All Patients</h4>
          <p className="text-sm text-slate-300 mt-1">Access complete patient records and screening history</p>
        </button>
      </div>

      {/* Recent Screenings */}
      <div className="bg-white border border-slate-200 rounded-lg shadow-sm overflow-hidden" data-testid="recent-patients">
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center">
            <FileText className="w-5 h-5 text-blue-600 mr-2" />
            <h4 className="font-bold text-slate-700">Recent Screenings</h4>
          </div>
          <span className="text-xs text-slate-400">Last 5 entries</span>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-6 py-3 text-left font-bold text-slate-500 uppercase tracking-wider text-xs">Patient ID</th>
                <th className="px-6 py-3 text-left font-bold text-slate-500 uppercase tracking-wider text-xs">Date</th>
                <th className="px-6 py-3 text-left font-bold text-slate-500 uppercase tracking-wider text-xs">Patient</th>
                <th className="px-6 py-3 text-center font-bold text-slate-500 uppercase tracking-wider text-xs">Result</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-slate-100">
              {(stats?.recentCases || stats?.recentPatients || []).slice(0, 5).map((item, index) => (
                <tr key={item.id || index} className="hover:bg-slate-50 transition-colors">
                  <td className="px-6 py-3 font-mono text-xs text-slate-600">{item.id || item.patientId}</td>
                  <td className="px-6 py-3 text-slate-600">{item.date}</td>
                  <td className="px-6 py-3 font-medium text-slate-800">{item.patientRef || item.name || "N/A"}</td>
                  <td className="px-6 py-3 text-center">
                    <span
                      className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
                        item.result === "High Risk" || item.result === "DEFICIENT"
                          ? "bg-red-100 text-red-800 border border-red-200"
                          : item.result === "Borderline" || item.result === "BORDERLINE"
                            ? "bg-amber-100 text-amber-800 border border-amber-200"
                            : "bg-green-100 text-green-800 border border-green-200"
                      }`}
                    >
                      {item.result}
                    </span>
                  </td>
                </tr>
              ))}
              {(!stats?.recentCases && !stats?.recentPatients) || (stats?.recentCases?.length === 0 && stats?.recentPatients?.length === 0) ? (
                <tr>
                  <td colSpan={4} className="px-6 py-8 text-center text-slate-400">
                    <FileText className="w-8 h-8 mx-auto mb-2 text-slate-300" />
                    <p>No recent screenings found</p>
                    <p className="text-xs mt-1">Start a new screening to see results here</p>
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default DoctorDashboard;
