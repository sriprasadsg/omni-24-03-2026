
import React from 'react';
import { ComplianceFramework } from '../types';
import { ShieldCheckIcon } from './icons';
import { NistCsfDetail } from './NistCsfDetail';

interface ComplianceStatusProps {
  frameworks: ComplianceFramework[];
}

const statusClasses: Record<ComplianceFramework['status'], { bg: string, text: string, progressBg: string }> = {
  Compliant: { bg: 'bg-green-100 dark:bg-green-900/50', text: 'text-green-600 dark:text-green-400', progressBg: 'bg-green-500' },
  Pending: { bg: 'bg-amber-100 dark:bg-amber-900/50', text: 'text-amber-600 dark:text-amber-400', progressBg: 'bg-amber-500' },
  'At Risk': { bg: 'bg-red-100 dark:bg-red-900/50', text: 'text-red-600 dark:text-red-400', progressBg: 'bg-red-500' },
};

export const ComplianceStatus: React.FC<ComplianceStatusProps> = ({ frameworks }) => {
  const nistFramework = frameworks.find(f => f.id === 'nistcsf');
  const otherFrameworks = frameworks.filter(f => f.id !== 'nistcsf');

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-semibold flex items-center">
            <ShieldCheckIcon className="mr-2 text-primary-500" />
            Compliance & Governance Posture
        </h3>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 p-4">
        {otherFrameworks.map(framework => {
          const classes = statusClasses[framework.status];
          return (
            <div key={framework.id} className={`p-4 rounded-lg border border-gray-200 dark:border-gray-700 ${classes.bg}`}>
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
  );
};