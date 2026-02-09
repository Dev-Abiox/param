import React, { useMemo } from 'react';
import { CBCRow, Flag } from '../types';

interface CBCTableProps {
  rows: CBCRow[];
  patientSex: 'M' | 'F';
  onValueChange: (key: string, value: string) => void;
  readOnly?: boolean;
}

const CBCTable: React.FC<CBCTableProps> = ({ rows, patientSex, onValueChange, readOnly = false }) => {
  
  const getFlag = (value: string, range: [number, number]): Flag => {
    if (value === '') return Flag.NORMAL;
    const num = parseFloat(value);
    if (isNaN(num)) return Flag.NORMAL;
    if (num < range[0]) return Flag.LOW;
    if (num > range[1]) return Flag.HIGH;
    return Flag.NORMAL;
  };

  const renderFlagBadge = (flag: Flag) => {
    switch (flag) {
      case Flag.HIGH:
        return <span className="inline-flex items-center justify-center w-5 h-5 text-[10px] font-bold text-red-700 bg-red-100 border border-red-200 rounded">H</span>;
      case Flag.LOW:
        return <span className="inline-flex items-center justify-center w-5 h-5 text-[10px] font-bold text-blue-700 bg-blue-100 border border-blue-200 rounded">L</span>;
      default:
        return null;
    }
  };

  return (
    <div className="bg-white border border-slate-300 shadow-sm rounded-sm overflow-hidden">
      <div className="bg-slate-100 border-b border-slate-200 px-4 py-2 flex justify-between items-center">
        <h3 className="font-semibold text-sm text-slate-700 uppercase tracking-tight">Hematology Panel</h3>
        <span className="text-xs text-slate-500 italic">Units: SI</span>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th scope="col" className="px-4 py-2 text-left font-semibold text-slate-600 w-1/3">Test Name</th>
              <th scope="col" className="px-4 py-2 text-right font-semibold text-slate-600 w-24">Result</th>
              <th scope="col" className="px-4 py-2 text-left font-semibold text-slate-600 w-20">Unit</th>
              <th scope="col" className="px-4 py-2 text-center font-semibold text-slate-600 w-32">Ref. Range</th>
              <th scope="col" className="px-4 py-2 text-center font-semibold text-slate-600 w-16">Flag</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {rows.map((row, idx) => {
              const range = patientSex === 'M' ? row.refRangeM : row.refRangeF;
              const flag = getFlag(row.value, range);
              const isFlagged = flag !== Flag.NORMAL;

              return (
                <tr key={row.key} className={`hover:bg-slate-50 transition-colors ${idx % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}`}>
                  <td className="px-4 py-1.5 text-slate-700 font-medium whitespace-nowrap border-r border-slate-100">
                    {row.test}
                  </td>
                  <td className="px-4 py-1.5 border-r border-slate-100">
                    <input
                      type="number"
                      value={row.value}
                      onChange={(e) => onValueChange(row.key, e.target.value)}
                      disabled={readOnly}
                      className={`w-full text-right bg-transparent focus:outline-none focus:ring-2 focus:ring-teal-500 rounded px-1 font-mono ${
                        isFlagged ? (flag === Flag.HIGH ? 'text-red-600 font-bold' : 'text-blue-600 font-bold') : 'text-slate-900'
                      }`}
                      placeholder="-"
                    />
                  </td>
                  <td className="px-4 py-1.5 text-slate-500 text-xs border-r border-slate-100">
                    {row.unit}
                  </td>
                  <td className="px-4 py-1.5 text-center text-slate-500 text-xs font-mono border-r border-slate-100">
                    {range[0]} - {range[1]}
                  </td>
                  <td className="px-4 py-1.5 text-center">
                    {renderFlagBadge(flag)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="bg-slate-50 px-4 py-2 border-t border-slate-200 text-[10px] text-slate-400 text-right">
        * Reference ranges based on WHO guidelines 2024
      </div>
    </div>
  );
};

export default CBCTable;
