import React, { useEffect, useState } from "react";
import { ChevronRight, FlaskConical, Users, FileText } from "lucide-react";
import { LisService } from "../services/api";

const LabList = ({ onSelectLab }) => {
  const [labs, setLabs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchLabs = async () => {
      setLoading(true);
      try {
        const data = await LisService.getLabs();
        setLabs(data);
      } catch (e) {
        console.error("Failed to load labs", e);
      } finally {
        setLoading(false);
      }
    };
    fetchLabs();
  }, []);

  return (
    <div className="space-y-6" data-testid="lab-list">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Laboratory Registry</h2>
          <p className="text-sm text-slate-500">Subscribed Pathology Labs and Diagnostic Centers</p>
        </div>
        <div className="p-2 bg-slate-100 rounded-md text-slate-500 flex items-center text-sm font-medium" data-testid="lab-count">
          <FlaskConical className="w-4 h-4 mr-2" />
          Total Active Labs: {labs.length}
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center h-64 text-slate-400" data-testid="lab-list-loading">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-teal-600 mb-3" />
          Loading registry...
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 gap-6">
          {labs.map((lab) => (
            <div
              key={lab.id}
              data-testid={`lab-card-${lab.id}`}
              onClick={() => onSelectLab(lab.code, lab.name)}
              className="bg-white border border-slate-200 rounded-lg p-6 shadow-sm hover:shadow-md hover:border-teal-300 cursor-pointer transition-all group relative"
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center space-x-4">
                  <div className="h-12 w-12 rounded-lg bg-teal-50 flex items-center justify-center text-teal-600 border border-teal-100 group-hover:bg-teal-600 group-hover:text-white transition-colors">
                    <FlaskConical className="w-6 h-6" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-slate-800 group-hover:text-teal-700 transition-colors">{lab.name}</h3>
                    <div className="flex items-center space-x-2 mt-1">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-slate-100 text-slate-500 border border-slate-200">{lab.tier}</span>
                      <span className="text-xs text-slate-400">ID: {lab.id}</span>
                    </div>
                  </div>
                </div>
                <div className="bg-slate-50 rounded-full p-2 group-hover:bg-teal-50">
                  <ChevronRight className="w-5 h-5 text-slate-400 group-hover:text-teal-600 transition-colors" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 border-t border-slate-100 pt-4">
                <div>
                  <span className="text-xs text-slate-400 uppercase font-semibold">Reg. Doctors</span>
                  <div className="flex items-center mt-1">
                    <Users className="w-4 h-4 text-slate-500 mr-2" />
                    <span className="font-mono font-bold text-slate-700">{lab.doctors}</span>
                  </div>
                </div>
                <div>
                  <span className="text-xs text-slate-400 uppercase font-semibold">Total Cases</span>
                  <div className="flex items-center mt-1">
                    <FileText className="w-4 h-4 text-slate-500 mr-2" />
                    <span className="font-mono font-bold text-slate-700">{lab.cases}</span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default LabList;
