import React, { useState } from 'react';
import { ComplianceFramework } from '../types';
import { ShieldCheckIcon } from './icons';
import { NistCsfDetail } from './NistCsfDetail';
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';

interface ComplianceStatusProps {
  frameworks: ComplianceFramework[];
}

const statusClasses: Record<ComplianceFramework['status'], { bg: string, text: string, progressBg: string }> = {
  Compliant: { bg: 'bg-green-100 dark:bg-green-900/50', text: 'text-green-600 dark:text-green-400', progressBg: 'bg-green-500' },
  Pending: { bg: 'bg-amber-100 dark:bg-amber-900/50', text: 'text-amber-600 dark:text-amber-400', progressBg: 'bg-amber-500' },
  'At Risk': { bg: 'bg-red-100 dark:bg-red-900/50', text: 'text-red-600 dark:text-red-400', progressBg: 'bg-red-500' },
};

const COLORS = {
  passed: '#10b981', // green-500
  failed: '#ef4444', // red-500
  pending: '#f59e0b', // amber-500
};

export const ComplianceStatus: React.FC<ComplianceStatusProps> = ({ frameworks }) => {
  const [selectedFramework, setSelectedFramework] = useState<ComplianceFramework | null>(null);
  const nistFramework = frameworks.find(f => f.id === 'nistcsf');
  const otherFrameworks = frameworks.filter(f => f.id !== 'nistcsf');

  const handleCardClick = (framework: ComplianceFramework) => {
    setSelectedFramework(framework);
  };

  const closeModal = () => {
    setSelectedFramework(null);
  };

  const getComplianceData = (framework: ComplianceFramework) => {
    // Calculate based on progress percentage
    const passed = framework.progress;
    const remaining = 100 - passed;
    // Split remaining between failed and pending based on status
    const failed = framework.status === 'At Risk' ? remaining * 0.7 : remaining * 0.3;
    const pending = remaining - failed;

    return [
      { name: 'Passed', value: Math.round(passed), count: Math.round(passed) },
      { name: 'Failed', value: Math.round(failed), count: Math.round(failed) },
      { name: 'Pending', value: Math.round(pending), count: Math.round(pending) },
    ].filter(item => item.value > 0);
  };

  return (
    <>
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-lg font-semibold flex items-center">
            <ShieldCheckIcon className="mr-2 text-primary-500" />
            Compliance & Governance Posture
          </h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 p-4">
          {otherFrameworks.map(framework => {
            const classes = statusClasses[framework.status] || statusClasses['Pending'];
            return (
              <div
                key={framework.id}
                className={`p-4 rounded-lg border border-gray-200 dark:border-gray-700 ${classes.bg} cursor-pointer hover:shadow-lg transition-shadow duration-200`}
                onClick={() => handleCardClick(framework)}
              >
                <div className="flex justify-between items-start">
                  <h4 className="font-bold text-gray-800 dark:text-white">{framework.shortName}</h4>
                  <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${classes.bg} ${classes.text}`}>{framework.status}</span>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 h-8">{framework.name}</p>
                <div className="mt-4">
                  <div className="flex justify-between mb-1">
                    <span className="text-xs font-medium text-gray-600 dark:text-gray-300">Progress</span>
                    <span className={`text-xs font-medium ${classes.text}`}>{framework.progress}%</span>
                  </div>
                  <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                    <div className={`${classes.progressBg} h-1.5 rounded-full`} style={{ width: `${framework.progress}%` }}></div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        {nistFramework && (
          <div className="p-4 border-t border-gray-200 dark:border-gray-700">
            <NistCsfDetail framework={nistFramework} />
          </div>
        )}
      </div>

      {/* Modal */}
      {selectedFramework && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" onClick={closeModal}>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-2xl max-w-3xl w-full mx-4 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            {/* Modal Header */}
            <div className="p-6 border-b border-gray-200 dark:border-gray-700 flex justify-between items-start">
              <div>
                <h2 className="text-2xl font-bold text-gray-800 dark:text-white">{selectedFramework.shortName}</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{selectedFramework.name}</p>
              </div>
              <button
                onClick={closeModal}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6">
              {/* Overall Progress */}
              <div className="mb-6 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Overall Progress</span>
                  <span className="text-2xl font-bold text-primary-600 dark:text-primary-400">{selectedFramework.progress}%</span>
                </div>
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3">
                  <div
                    className="bg-primary-500 h-3 rounded-full transition-all duration-300"
                    style={{ width: `${selectedFramework.progress}%` }}
                  ></div>
                </div>
              </div>

              {/* Pie Chart */}
              <div className="mb-6">
                <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4">Compliance Status Breakdown</h3>
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={getComplianceData(selectedFramework)}
                      cx="50%"
                      cy="50%"
                      outerRadius={100}
                      fill="#8884d8"
                      dataKey="value"
                      label={(props) => {
                        const RADIAN = Math.PI / 180;
                        const { cx, cy, midAngle, outerRadius, percent } = props;
                        const radius = outerRadius + 25;
                        const x = cx + radius * Math.cos(-midAngle * RADIAN);
                        const y = cy + radius * Math.sin(-midAngle * RADIAN);

                        return (
                          <text
                            x={x}
                            y={y}
                            fill="currentColor"
                            textAnchor={x > cx ? 'start' : 'end'}
                            dominantBaseline="central"
                            className="text-sm font-bold"
                          >
                            {`${(percent * 100).toFixed(0)}%`}
                          </text>
                        );
                      }}
                      labelLine={{
                        stroke: '#9ca3af',
                        strokeWidth: 1
                      }}
                    >
                      {getComplianceData(selectedFramework).map((entry, index) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={entry.name === 'Passed' ? COLORS.passed : entry.name === 'Failed' ? COLORS.failed : COLORS.pending}
                        />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend wrapperStyle={{ fontSize: '12px', fontWeight: '600' }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              {/* Missing Controls Summary */}
              <div className="space-y-4">
                <h3 className="text-lg font-semibold text-gray-800 dark:text-white">Compliance Gaps</h3>

                {getComplianceData(selectedFramework).map((item) => {
                  if (item.name === 'Passed') return null;

                  const bgColor = item.name === 'Failed' ? 'bg-red-50 dark:bg-red-900/20' : 'bg-amber-50 dark:bg-amber-900/20';
                  const textColor = item.name === 'Failed' ? 'text-red-700 dark:text-red-400' : 'text-amber-700 dark:text-amber-400';
                  const iconColor = item.name === 'Failed' ? 'text-red-500' : 'text-amber-500';

                  return (
                    <div key={item.name} className={`p-4 rounded-lg ${bgColor}`}>
                      <div className="flex items-start">
                        <svg className={`w-5 h-5 ${iconColor} mt-0.5 mr-3 flex-shrink-0`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                        <div className="flex-1">
                          <h4 className={`font-semibold ${textColor} mb-1`}>{item.name} Controls</h4>
                          <p className="text-sm text-gray-600 dark:text-gray-400">
                            Approximately {item.count} controls are {item.name.toLowerCase()}
                          </p>
                          <p className="text-xs text-gray-500 dark:text-gray-500 mt-2">
                            {item.name === 'Failed'
                              ? 'These controls require immediate attention and remediation.'
                              : 'These controls are awaiting implementation or verification.'}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-6 border-t border-gray-200 dark:border-gray-700 flex justify-end">
              <button
                onClick={closeModal}
                className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
