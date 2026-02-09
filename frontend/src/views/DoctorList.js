import React, { useEffect, useState } from "react";
import { LisService } from "../services/api";
import { User, FileText, ChevronRight, Stethoscope, ArrowLeft } from "lucide-react";

const DoctorList = ({ onSelectDoctor, labId, labName, onBack }) => {
  const [doctors, setDoctors] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDoctors = async () => {
      setLoading(true);
      try {
        const data = await LisService.getDoctors(labId);
        setDoctors(data);
      } catch (e) {
        console.error("Failed to load doctors", e);
      } finally {
        setLoading(false);
      }
    };
    fetchDoctors();
  }, [labId]);

  return (
    <div className="space-y-6" data-testid="doctor-list">
      {onBack && (
        <button data-testid="back-to-labs" onClick={onBack} className="flex items-center text-sm text-slate-500 hover:text-teal-600 mb-2 transition-colors">
          <ArrowLeft className="w-4 h-4 mr-1" /> Back to Lab Registry
        </button>
      )}

      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">{labName ? `${labName}: Doctor Registry` : "Referring Doctors"}</h2>
          <p className="text-sm text-slate-500">{labName ? "Physicians associated with this laboratory" : "Select a physician to view their patient records"}</p>
        </div>
        <div className="p-2 bg-slate-100 rounded-md text-slate-500 flex items-center text-sm font-medium" data-testid="doctor-count">
          <Stethoscope className="w-4 h-4 mr-2" />
          Active Doctors: {doctors.length}
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center h-64 text-slate-400" data-testid="doctor-list-loading">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-teal-600 mb-3" />
          Loading physicians...
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {doctors.map((doc) => (
            <div
              key={doc.id}
              data-testid={`doctor-card-${doc.id}`}
              onClick={() => onSelectDoctor(doc.code, doc.name)}
              className="bg-white border border-slate-200 rounded-lg p-5 shadow-sm hover:shadow-md hover:border-teal-300 cursor-pointer transition-all group relative overflow-hidden"
            >
              <div className="absolute top-0 left-0 w-1 h-full bg-slate-200 group-hover:bg-teal-500 transition-colors" />
              <div className="flex items-start justify-between">
                <div className="flex items-center space-x-3">
                  <div className="h-10 w-10 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 group-hover:bg-teal-50 group-hover:text-teal-600 transition-colors">
                    <User className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-bold text-slate-800 group-hover:text-teal-700 transition-colors">{doc.name}</h3>
                    <p className="text-xs text-slate-500">{doc.dept}</p>
                  </div>
                </div>
                <ChevronRight className="w-5 h-5 text-slate-300 group-hover:text-teal-500 transition-colors" />
              </div>
              <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
                <span className="text-slate-400 font-medium">Referred Cases</span>
                <span className="flex items-center text-slate-700 font-bold bg-slate-50 px-2 py-1 rounded">
                  <FileText className="w-3 h-3 mr-1 text-slate-400" />
                  {doc.cases}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default DoctorList;
