import React, { useEffect, useState } from 'react';
import { LisService } from '../services/api';
import { ScreeningLabel } from '../types';
import { Search, Filter, FileText, Download, Eye, Calendar, User, ArrowLeft } from 'lucide-react';

interface PatientRecordsProps {
  doctorId?: string; // Optional: if provided, filters by doctor. If null, assumes "my records"
  doctorName?: string;
  onBack?: () => void;
}

const PatientRecords: React.FC<PatientRecordsProps> = ({ doctorId, doctorName, onBack }) => {
  const [records, setRecords] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    const fetchRecords = async () => {
      setLoading(true);
      try {
        const data = await LisService.getPatientRecords(doctorId);
        setRecords(data);
      } catch (e) {
        console.error("Failed to load records", e);
      } finally {
        setLoading(false);
      }
    };
    fetchRecords();
  }, [doctorId]);

  const filteredRecords = records.filter(r => 
    r.name.toLowerCase().includes(searchTerm.toLowerCase()) || 
    r.patientId.toLowerCase().includes(searchTerm.toLowerCase()) ||
    r.labId.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const getStatusBadge = (status: ScreeningLabel) => {
    switch (status) {
      case ScreeningLabel.NORMAL:
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 border border-green-200">Normal</span>;
      case ScreeningLabel.BORDERLINE:
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 border border-amber-200">Borderline</span>;
      case ScreeningLabel.DEFICIENT:
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 border border-red-200">Deficient</span>;
      default:
        return null;
    }
  };

  return (
    <div className="space-y-6">
      {onBack && (
        <button 
          onClick={onBack}
          className="flex items-center text-sm text-slate-500 hover:text-teal-600 mb-2 transition-colors"
        >
          <ArrowLeft className="w-4 h-4 mr-1" /> Back to Doctor Registry
        </button>
      )}

      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">
            {doctorName ? `Records: ${doctorName}` : 'Patient Records'}
          </h2>
          <p className="text-sm text-slate-500">History of screening results and reports</p>
        </div>
        <div className="flex items-center space-x-2 w-full sm:w-auto">
          <div className="relative flex-1 sm:flex-none sm:w-64">
             <Search className="w-4 h-4 absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400" />
             <input 
               type="text" 
               placeholder="Search Name, ID, or Lab Ref..." 
               value={searchTerm}
               onChange={(e) => setSearchTerm(e.target.value)}
               className="w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-md focus:outline-none focus:ring-1 focus:ring-teal-500 bg-white shadow-sm" 
             />
          </div>
          <button className="p-2 border border-slate-300 rounded-md bg-white hover:bg-slate-50 text-slate-600">
            <Filter className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-sm shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-slate-500">
             <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-teal-600 mx-auto mb-3"></div>
             Loading records...
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-6 py-3 text-left font-bold text-slate-500 uppercase tracking-wider text-xs w-32">Patient ID</th>
                  <th className="px-6 py-3 text-left font-bold text-slate-500 uppercase tracking-wider text-xs">Patient Details</th>
                  <th className="px-6 py-3 text-left font-bold text-slate-500 uppercase tracking-wider text-xs">Lab Ref / Date</th>
                  <th className="px-6 py-3 text-center font-bold text-slate-500 uppercase tracking-wider text-xs">Screening Result</th>
                  <th className="px-6 py-3 text-right font-bold text-slate-500 uppercase tracking-wider text-xs">Actions</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-slate-100">
                {filteredRecords.length > 0 ? (
                  filteredRecords.map((record) => (
                    <tr key={record.id} className="hover:bg-slate-50 transition-colors group">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm font-mono font-medium text-slate-700">{record.patientId}</div>
                        <div className="text-xs text-slate-400">Case: {record.id}</div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center">
                          <div className="h-8 w-8 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 mr-3">
                            <User className="w-4 h-4" />
                          </div>
                          <div>
                            <div className="text-sm font-bold text-slate-900">{record.name}</div>
                            <div className="text-xs text-slate-500">{record.age} Y / {record.sex}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                         <div className="text-sm text-slate-600 font-mono">{record.labId}</div>
                         <div className="flex items-center text-xs text-slate-400 mt-0.5">
                           <Calendar className="w-3 h-3 mr-1" />
                           {record.date}
                         </div>
                      </td>
                      <td className="px-6 py-4 text-center">
                        {getStatusBadge(record.result)}
                      </td>
                      <td className="px-6 py-4 text-right whitespace-nowrap text-sm font-medium">
                        <div className="flex justify-end space-x-2">
                          <button 
                            className="text-slate-400 hover:text-teal-600 p-1 rounded hover:bg-teal-50 transition-colors"
                            title="View Details"
                          >
                            <Eye className="w-4 h-4" />
                          </button>
                          <button 
                            className="text-slate-400 hover:text-teal-600 p-1 rounded hover:bg-teal-50 transition-colors"
                            title="Download Report"
                          >
                            <Download className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="px-6 py-10 text-center text-slate-400">
                      <FileText className="w-10 h-10 mx-auto mb-2 text-slate-300" />
                      <p>No records found matching "{searchTerm}"</p>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
        <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 text-xs text-slate-500 flex justify-between items-center">
          <span>Total Records: {records.length}</span>
          <div className="flex space-x-2">
            <button className="px-2 py-1 border border-slate-300 rounded bg-white hover:bg-slate-50 disabled:opacity-50" disabled>Previous</button>
            <button className="px-2 py-1 border border-slate-300 rounded bg-white hover:bg-slate-50 disabled:opacity-50" disabled>Next</button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PatientRecords;