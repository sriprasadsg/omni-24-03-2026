import React from 'react';
import { ComplianceFramework } from '../types';
import { BookOpenCheckIcon } from './icons';

interface NistCsfDetailProps {
  framework: ComplianceFramework;
}

const functionColors: Record<string, string> = {
    identify: 'bg-blue-500',
    protect: 'bg-green-500',
    detect: 'bg-amber-500',
    respond: 'bg-orange-500',
    recover: 'bg-purple-500',
};

export const NistCsfDetail: React.FC<NistCsfDetailProps> = ({ framework }) => {
  if (!framework.nistFunctions) return null;

  return (
    <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
      <h4 className="text-base font-semibold flex items-center text-gray-800 dark:text-white mb-1">
        <BookOpenCheckIcon className="mr-2 text-primary-500" size={20} />
        {framework.name}
      </h4>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">{framework.description}</p>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {framework.nistFunctions.map(func => (
          <div key={func.id}>
            <div className="flex justify-between items-baseline mb-1">
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{func.name}</span>
              <span className="text-sm font-bold text-gray-800 dark:text-gray-200">{func.progress}%</span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
              <div className={`${functionColors[func.id]} h-2 rounded-full`} style={{ width: `${func.progress}%` }}></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
