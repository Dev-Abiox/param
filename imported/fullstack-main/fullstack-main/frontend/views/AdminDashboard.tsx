import React, { useEffect, useState } from 'react';
import { LisService } from '../services/api';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, AreaChart, Area, CartesianGrid } from 'recharts';
import { Users, FileText, AlertTriangle, TrendingUp, Search, Download, Brain, Activity, Database, Server } from 'lucide-react';

const AdminDashboard: React.FC = () => {
  const [stats, setStats] = useState<any>(null);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    LisService.getStats().then(setStats);
  }, []);

  const handleExportCSV = () => {
    if (!stats || !stats.recentCases) return;
    
    const headers = ["Case ID", "Date", "Patient Ref", "MCV (fL)", "Screening Result"];
    const rows = stats.recentCases.map((c: any) => [
      c.id, 
      c.date, 
      c.patientRef, 
      c.mcv, 
      c.result
    ]);

    // Explicit newline character for CSV
    const csvContent = "data:text/csv;charset=utf-8," 
      + [headers.join(","), ...rows.map((r: any[]) => r.join(","))].join('\n');

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `clinomic_labs_export_${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (!stats) return (
    <div className="flex flex-col items-center justify-center h-96 text-slate-400">
      <Activity className="w-8 h-8 animate-spin mb-4 text-teal-600" />
      <p>Loading analytics data...</p>
    </div>
  );

  const filteredCases = stats.recentCases.filter((c: any) => 
    c.id.toLowerCase().includes(searchTerm.toLowerCase()) || 
    c.patientRef.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Administrator Dashboard</h2>
          <p className="text-sm text-slate-500">System Status, ML Performance & Case Management</p>
        </div>
        <div className="flex items-center space-x-3">
             <div className="flex items-center px-4 py-2 bg-slate-800 text-teal-400 rounded-md shadow-sm border border-slate-700">
               <Server className="w-4 h-4 mr-2" />
               <div className="text-xs text-left">
                 <div className="font-bold text-white">Backend Status</div>
                 <div className="text-teal-400">Online • {stats.modelMetrics.version}</div>
               </div>
             </div>
        </div>
      </div>

      {/* Row 1: Operational Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Total User Screenings */}
        <div className="bg-white p-5 rounded-sm border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wide">Total User Screenings</p>
            <h3 className="text-3xl font-extrabold text-slate-800 mt-1">{stats.totalCases.toLocaleString()}</h3>
            <p className="text-xs text-green-600 font-medium mt-1 flex items-center">
              <TrendingUp className="w-3 h-3 mr-1" /> +{stats.dailyTests} in last 24h
            </p>
          </div>
          <div className="p-3 rounded-full bg-teal-50 text-teal-600 border border-teal-100">
            <Users className="w-6 h-6" />
          </div>
        </div>

        {/* ML Model Accuracy */}
        <div className="bg-white p-5 rounded-sm border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wide">Model Accuracy</p>
            <h3 className="text-3xl font-extrabold text-slate-800 mt-1">{stats.modelMetrics.accuracy}%</h3>
            <p className="text-xs text-slate-500 mt-1">Validation Set #412</p>
          </div>
          <div className="p-3 rounded-full bg-violet-50 text-violet-600 border border-violet-100">
            <Brain className="w-6 h-6" />
          </div>
        </div>

        {/* Flagged Risks */}
        <div className="bg-white p-5 rounded-sm border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wide">High Risk Detected</p>
            <h3 className="text-3xl font-extrabold text-slate-800 mt-1">{stats.distribution[2].value}</h3>
            <p className="text-xs text-red-500 font-medium mt-1">
               {((stats.distribution[2].value / stats.totalCases) * 100).toFixed(1)}% of total cases
            </p>
          </div>
          <div className="p-3 rounded-full bg-red-50 text-red-600 border border-red-100">
            <AlertTriangle className="w-6 h-6" />
          </div>
        </div>

         {/* Model Version/Health */}
         <div className="bg-white p-5 rounded-sm border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wide">Backend API Latency</p>
            <h3 className="text-3xl font-extrabold text-slate-800 mt-1">45ms</h3>
            <p className="text-xs text-green-600 font-medium mt-1">Optimal Performance</p>
          </div>
          <div className="p-3 rounded-full bg-blue-50 text-blue-600 border border-blue-100">
            <Activity className="w-6 h-6" />
          </div>
        </div>
      </div>

      {/* Row 2: ML Deep Dive & Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* ML Metrics Panel */}
        <div className="bg-white rounded-sm border border-slate-200 shadow-sm flex flex-col">
          <div className="px-6 py-4 border-b border-slate-100">
             <h4 className="font-bold text-slate-700 flex items-center">
               <Brain className="w-4 h-4 mr-2 text-violet-500" />
               Backend ML Metrics
             </h4>
          </div>
          <div className="p-6 flex-1 flex flex-col justify-center space-y-6">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-500">Recall (Sensitivity)</span>
                <span className="font-bold text-slate-800">{stats.modelMetrics.recall}%</span>
              </div>
              <div className="w-full bg-slate-100 rounded-full h-2">
                <div className="bg-violet-500 h-2 rounded-full" style={{ width: `${stats.modelMetrics.recall}%` }}></div>
              </div>
              <p className="text-[10px] text-slate-400 mt-1">Crucial for minimizing false negatives in screening.</p>
            </div>

            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-500">Precision</span>
                <span className="font-bold text-slate-800">{stats.modelMetrics.precision}%</span>
              </div>
              <div className="w-full bg-slate-100 rounded-full h-2">
                <div className="bg-violet-400 h-2 rounded-full" style={{ width: `${stats.modelMetrics.precision}%` }}></div>
              </div>
            </div>

            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-500">F1 Score</span>
                <span className="font-bold text-slate-800">{stats.modelMetrics.f1Score}%</span>
              </div>
              <div className="w-full bg-slate-100 rounded-full h-2">
                <div className="bg-violet-300 h-2 rounded-full" style={{ width: `${stats.modelMetrics.f1Score}%` }}></div>
              </div>
            </div>

            <div className="pt-4 border-t border-slate-100 grid grid-cols-2 gap-4 text-center">
              <div>
                <p className="text-xs text-slate-400">AUC - ROC</p>
                <p className="text-xl font-bold text-slate-800">{stats.modelMetrics.auc}</p>
              </div>
              <div>
                 <p className="text-xs text-slate-400">Training Loss</p>
                 <p className="text-xl font-bold text-slate-800">0.024</p>
              </div>
            </div>
          </div>
        </div>

        {/* Result Distribution Chart */}
        <div className="lg:col-span-2 bg-white p-6 rounded-sm border border-slate-200 shadow-sm">
          <h4 className="text-sm font-bold text-slate-700 mb-6">Screening Outcome Distribution</h4>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats.distribution} barSize={60}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fill: '#64748b'}} />
                <YAxis axisLine={false} tickLine={false} tick={{fill: '#64748b'}} />
                <Tooltip 
                  cursor={{fill: '#f8fafc'}} 
                  contentStyle={{borderRadius: '4px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)'}}
                />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {stats.distribution.map((entry: any, index: number) => (
                    <Cell key={`cell-${index}`} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Row 3: Data Export Table */}
      <div className="bg-white border border-slate-200 rounded-sm shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex flex-col sm:flex-row justify-between items-center gap-4">
          <div className="flex items-center">
            <Database className="w-5 h-5 text-teal-600 mr-2" />
            <h4 className="font-bold text-slate-700">Case Database</h4>
          </div>
          
          <div className="flex items-center gap-3 w-full sm:w-auto">
            <div className="relative flex-1 sm:flex-none">
               <Search className="w-4 h-4 absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400" />
               <input 
                 type="text" 
                 placeholder="Search ID or Patient..." 
                 value={searchTerm}
                 onChange={(e) => setSearchTerm(e.target.value)}
                 className="pl-9 pr-3 py-1.5 text-sm border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-teal-500 w-full" 
               />
            </div>
            <button 
              onClick={handleExportCSV}
              className="flex items-center px-4 py-1.5 bg-slate-800 text-white text-sm font-medium rounded hover:bg-slate-700 transition-colors shadow-sm whitespace-nowrap"
            >
              <Download className="w-4 h-4 mr-2" /> Export CSV
            </button>
          </div>
        </div>
        
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-6 py-3 text-left font-bold text-slate-500 uppercase tracking-wider text-xs">Case ID</th>
                <th className="px-6 py-3 text-left font-bold text-slate-500 uppercase tracking-wider text-xs">Date</th>
                <th className="px-6 py-3 text-left font-bold text-slate-500 uppercase tracking-wider text-xs">Patient Ref</th>
                <th className="px-6 py-3 text-left font-bold text-slate-500 uppercase tracking-wider text-xs">MCV (fL)</th>
                <th className="px-6 py-3 text-center font-bold text-slate-500 uppercase tracking-wider text-xs">Result</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-slate-100">
              {filteredCases.slice(0, 10).map((item: any) => (
                <tr key={item.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-6 py-3 font-mono text-xs text-slate-600">{item.id}</td>
                  <td className="px-6 py-3 text-slate-600">{item.date}</td>
                  <td className="px-6 py-3 font-medium text-slate-800">{item.patientRef}</td>
                  <td className="px-6 py-3 text-slate-600 font-mono">{item.mcv}</td>
                  <td className="px-6 py-3 text-center">
                    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
                      item.result === 'High Risk' 
                        ? 'bg-red-100 text-red-800 border border-red-200' 
                        : item.result === 'Borderline' 
                          ? 'bg-amber-100 text-amber-800 border border-amber-200' 
                          : 'bg-green-100 text-green-800 border border-green-200'
                    }`}>
                      {item.result}
                    </span>
                  </td>
                </tr>
              ))}
              {filteredCases.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-slate-400">
                    No cases found matching your search.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 text-xs text-slate-500 flex justify-between items-center">
          <span>Showing recent 10 of {stats.recentCases.length} entries</span>
          <span>Data synced: Just now</span>
        </div>
      </div>
    </div>
  );
};

export default AdminDashboard;