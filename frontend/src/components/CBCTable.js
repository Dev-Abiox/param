import React from "react";
import { Flag } from "../types";

const CBCTable = ({ rows, patientSex, onValueChange, readOnly = false }) => {
  const getFlag = (value, range) => {
    if (value === "") return Flag.NORMAL;
    const num = parseFloat(value);
    if (Number.isNaN(num)) return Flag.NORMAL;
    if (num < range[0]) return Flag.LOW;
    if (num > range[1]) return Flag.HIGH;
    return Flag.NORMAL;
  };

  const renderFlagBadge = (flag) => {
    switch (flag) {
      case Flag.HIGH:
        return <span className="inline-flex items-center justify-center w-5 h-5 text-[10px] font-bold text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded">H</span>;
      case Flag.LOW:
        return <span className="inline-flex items-center justify-center w-5 h-5 text-[10px] font-bold text-blue-700 dark:text-blue-400 bg-blue-100 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded">L</span>;
      default:
        return null;
    }
  };

  return (
    <div data-testid="cbc-table" className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 shadow-sm rounded-sm overflow-hidden">
      <div className="bg-slate-100 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 px-4 py-2 flex justify-between items-center">
        <h3 className="font-semibold text-sm text-slate-700 dark:text-slate-300 uppercase tracking-tight">Hematology Panel</h3>
        <span className="text-xs text-slate-500 dark:text-slate-400 italic">Units: SI</span>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-700 text-sm">
          <thead className="bg-slate-50 dark:bg-slate-800">
            <tr>
              <th scope="col" className="px-4 py-2 text-left font-semibold text-slate-600 dark:text-slate-300">Test Name</th>
              <th scope="col" className="px-4 py-2 text-left font-semibold text-slate-600 dark:text-slate-300 w-28">Result</th>
              <th scope="col" className="px-4 py-2 text-left font-semibold text-slate-600 dark:text-slate-300 w-24">Unit</th>
              <th scope="col" className="px-4 py-2 text-center font-semibold text-slate-600 dark:text-slate-300 w-32">Ref. Range</th>
              <th scope="col" className="px-4 py-2 text-center font-semibold text-slate-600 dark:text-slate-300 w-14">Flag</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-700 bg-white dark:bg-slate-900">
            {rows.map((row, idx) => {
              const range = patientSex === "M" ? row.refRangeM : row.refRangeF;
              const flag = getFlag(row.value, range);
              const isFlagged = flag !== Flag.NORMAL;

              return (
                <tr key={row.key} className={`hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors ${idx % 2 === 0 ? "bg-white dark:bg-slate-900" : "bg-slate-50/50 dark:bg-slate-800/50"}`}>
                  <td className="px-4 py-1.5 text-slate-700 dark:text-slate-300 font-medium whitespace-nowrap border-r border-slate-100 dark:border-slate-700">{row.test}</td>
                  <td className="px-2 py-1.5 border-r border-slate-100 dark:border-slate-700">
                    <input
                      data-testid={`cbc-input-${row.key}`}
                      type="number"
                      value={row.value}
                      onChange={(e) => onValueChange(row.key, e.target.value)}
                      disabled={readOnly}
                      className={`w-full text-left bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 rounded px-2 py-1 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500 disabled:bg-slate-100 dark:disabled:bg-slate-700 disabled:cursor-not-allowed ${
                        isFlagged ? (flag === Flag.HIGH ? "text-red-600 dark:text-red-400 font-bold" : "text-blue-600 font-bold") : "text-slate-900 dark:text-slate-100"
                      }`}
                      placeholder="0.0"
                    />
                  </td>
                  <td className="px-4 py-1.5 text-slate-500 dark:text-slate-400 text-xs border-r border-slate-100 dark:border-slate-700">{row.unit}</td>
                  <td className="px-4 py-1.5 text-center text-slate-500 dark:text-slate-400 text-xs font-mono border-r border-slate-100 dark:border-slate-700">{range[0]} - {range[1]}</td>
                  <td className="px-4 py-1.5 text-center">{renderFlagBadge(flag)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="bg-slate-50 dark:bg-slate-800 px-4 py-2 border-t border-slate-200 dark:border-slate-700 text-[10px] text-slate-400 dark:text-slate-500 text-right">* Reference ranges based on WHO guidelines 2024</div>
    </div>
  );
};

export default CBCTable;
