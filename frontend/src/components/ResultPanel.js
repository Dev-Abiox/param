import React, { useState, useEffect } from "react";
import { AlertTriangle, CheckCircle, AlertOctagon, FileText, Download, Printer } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LabelList } from "recharts";
import { ScreeningLabel } from "../types";
import { generateReport } from "@/lib/generateReport";
import { LisService } from "../services/api";

const ResultPanel = ({ result, patient, cbcRows }) => {
  const [shapData, setShapData] = useState(null);
  const [shapLoading, setShapLoading] = useState(false);

  useEffect(() => {
    if (result?.id) {
      setShapLoading(true);
      LisService.getExplanation(result.id)
        .then(data => setShapData(data.features))
        .catch(() => setShapData(null))
        .finally(() => setShapLoading(false));
    }
  }, [result?.id]);

  const generateDoc = () => generateReport(patient, result, cbcRows);

  const handleDownloadPDF = async () => {
    const doc = await generateDoc();
    doc.save(`ClinomicLabs_Report_${patient.id}.pdf`);
  };

  const handlePrint = async () => {
    const doc = await generateDoc();
    doc.autoPrint();
    const blob = doc.output("blob");
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
  };

  const getBadge = (label) => {
    const pNormal = (result.probabilities.normal * 100).toFixed(1);
    const pBorder = (result.probabilities.borderline * 100).toFixed(1);
    const pDeficient = (result.probabilities.deficient * 100).toFixed(1);

    const breakdown = (
      <div className="mt-1 text-xs font-medium opacity-90">
        N: {pNormal}% | B: {pBorder}% | D: {pDeficient}%
      </div>
    );

    switch (label) {
      case ScreeningLabel.NORMAL:
        return (
          <div className="flex items-center space-x-2 bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded-md shadow-sm" data-testid="result-badge-normal">
            <CheckCircle className="w-6 h-6 text-green-600" />
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-green-600">Screening Result</p>
              <h3 className="text-xl font-bold">Low Risk (Normal)</h3>
              {breakdown}
            </div>
          </div>
        );
      case ScreeningLabel.BORDERLINE:
        return (
          <div className="flex items-center space-x-2 bg-amber-50 border border-amber-200 text-amber-800 px-4 py-3 rounded-md shadow-sm" data-testid="result-badge-borderline">
            <AlertTriangle className="w-6 h-6 text-amber-600" />
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-amber-600">Screening Result</p>
              <h3 className="text-xl font-bold">Borderline / Indeterminate</h3>
              {breakdown}
            </div>
          </div>
        );
      case ScreeningLabel.DEFICIENT:
      default:
        return (
          <div className="flex items-center space-x-2 bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-md shadow-sm" data-testid="result-badge-deficient">
            <AlertOctagon className="w-6 h-6 text-red-600" />
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-red-600">Screening Result</p>
              <h3 className="text-xl font-bold">High Risk (Deficiency)</h3>
              {breakdown}
            </div>
          </div>
        );
    }
  };

  const chartData = [
    { name: "Normal", value: parseFloat((result.probabilities.normal * 100).toFixed(1)) },
    { name: "Borderline", value: parseFloat((result.probabilities.borderline * 100).toFixed(1)) },
    { name: "Deficient", value: parseFloat((result.probabilities.deficient * 100).toFixed(1)) },
  ];

  const getBarColor = (index) => {
    if (index === 0) return "#22c55e";
    if (index === 1) return "#f59e0b";
    return "#ef4444";
  };

  return (
    <div data-testid="result-panel" className="bg-white border border-slate-300 shadow-sm rounded-sm p-5 space-y-6">
      <div className="flex justify-between items-start">
        <h2 className="text-lg font-bold text-slate-800 flex items-center">
          <FileText className="w-5 h-5 mr-2 text-teal-600" />
          Screening Analysis Report
        </h2>
        <div className="flex space-x-2">
          <button
            data-testid="print-report-button"
            onClick={handlePrint}
            className="flex items-center px-3 py-1.5 text-xs font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded border border-slate-200"
          >
            <Printer className="w-3.5 h-3.5 mr-1.5" /> Print
          </button>
          <button
            data-testid="download-pdf-button"
            onClick={handleDownloadPDF}
            className="flex items-center px-3 py-1.5 text-xs font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded border border-slate-200"
          >
            <Download className="w-3.5 h-3.5 mr-1.5" /> PDF
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-4">
          {getBadge(result.label)}

          <div className="bg-slate-50 p-4 rounded border border-slate-200">
            <h4 className="text-sm font-semibold text-slate-700 mb-2 border-b border-slate-200 pb-2">Clinical Narrative</h4>
            {result.narrative ? (
              result.narrative.split('\n\n').map((para, i) => (
                <p key={i} className="text-sm text-slate-800 leading-relaxed mb-2 last:mb-0">{para}</p>
              ))
            ) : (
              <p className="text-sm text-slate-800 leading-relaxed italic">"{result.interpretation}"</p>
            )}
          </div>

          <div className="bg-blue-50 p-4 rounded border border-blue-100">
            <h4 className="text-sm font-semibold text-blue-800 mb-2 border-b border-blue-200 pb-2">Recommendation</h4>
            <p className="text-sm text-blue-900 font-medium">{result.recommendation}</p>
          </div>
        </div>

        <div className="space-y-4">
          <div className="border border-slate-200 rounded p-4 bg-white">
            <h4 className="text-xs font-semibold text-slate-500 uppercase mb-4 text-center">Model Confidence Probabilities</h4>
            <div className="h-48 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 30, left: 40, bottom: 5 }}>
                  <XAxis type="number" domain={[0, 100]} hide />
                  <YAxis dataKey="name" type="category" tick={{ fontSize: 12 }} width={80} />
                  <Tooltip cursor={{ fill: "transparent" }} contentStyle={{ fontSize: "12px" }} />
                  <Bar dataKey="value" barSize={24} radius={[0, 4, 4, 0]} background={{ fill: "#f1f5f9" }}>
                    <LabelList dataKey="value" position="right" formatter={(val) => `${val}%`} />
                    {chartData.map((entry, index) => (
                      <Cell key={`cell-${entry.name}`} fill={getBarColor(index)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {shapData && shapData.length > 0 && (
            <div className="border border-slate-200 rounded p-4 bg-white">
              <h4 className="text-xs font-semibold text-slate-500 uppercase mb-4 text-center">
                Feature Importance (SHAP)
              </h4>
              <div style={{ height: Math.max(200, shapData.slice(0, 10).length * 28) }} className="w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={shapData.slice(0, 10)}
                    layout="vertical"
                    margin={{ top: 5, right: 30, left: 80, bottom: 5 }}
                  >
                    <XAxis type="number" />
                    <YAxis dataKey="feature" type="category" tick={{ fontSize: 11 }} width={80} />
                    <Tooltip contentStyle={{ fontSize: "12px" }} />
                    <Bar dataKey="shap_value" barSize={18} radius={[0, 4, 4, 0]}>
                      {shapData.slice(0, 10).map((entry, index) => (
                        <Cell
                          key={`shap-${index}`}
                          fill={entry.shap_value > 0 ? "#ef4444" : "#22c55e"}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="text-xs text-slate-400 text-center mt-2">
                Red = increases risk, Green = decreases risk
              </p>
            </div>
          )}
        </div>
      </div>

      <div>
        <h4 className="text-sm font-bold text-slate-700 mb-3">Calculated Hematological Indices</h4>
        <div className="overflow-hidden border border-slate-200 rounded-sm">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-4 py-2 text-left font-medium text-slate-600">Index</th>
                <th className="px-4 py-2 text-right font-medium text-slate-600">Value</th>
                <th className="px-4 py-2 text-left font-medium text-slate-600">Clinical Significance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              <tr>
                <td className="px-4 py-2 font-medium text-slate-800">Mentzer Index</td>
                <td className="px-4 py-2 text-right font-mono">{result.indices.mentzer}</td>
                <td className="px-4 py-2 text-slate-500 text-xs">{result.indices.mentzer > 13 ? "Suggests Iron Deficiency" : "Suggests Thalassemia Trait"} (if microcytic)</td>
              </tr>
              <tr>
                <td className="px-4 py-2 font-medium text-slate-800">Green & King Index</td>
                <td className="px-4 py-2 text-right font-mono">{result.indices.greenKing}</td>
                <td className="px-4 py-2 text-slate-500 text-xs">Used for differentiating IDA vs Thalassemia</td>
              </tr>
              <tr>
                <td className="px-4 py-2 font-medium text-slate-800">NLR (Neutrophil/Lymphocyte)</td>
                <td className="px-4 py-2 text-right font-mono">{result.indices.nlr}</td>
                <td className="px-4 py-2 text-slate-500 text-xs">Inflammatory marker</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default ResultPanel;
