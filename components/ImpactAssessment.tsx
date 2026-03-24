import React from 'react';
import { AiSystem } from '../types';
import { ClipboardCheckIcon } from './icons';

interface ImpactAssessmentProps {
  system: AiSystem;
}

export const ImpactAssessment: React.FC<ImpactAssessmentProps> = ({ system }) => {
  const { impactAssessment, lastAssessmentDate } = system;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
        <h3 className="text-lg font-semibold flex items-center">
          <ClipboardCheckIcon className="mr-2 text-primary-500" />
          AI Impact Assessment
        </h3>
        <span className="text-xs text-gray-500 dark:text-gray-400">Last updated: {lastAssessmentDate}</span>
      </div>
      <div className="p-4 space-y-4">
        <div>
            <h4 className="font-semibold text-gray-700 dark:text-gray-300">Assessment Summary</h4>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{impactAssessment.summary}</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
                <h4 className="font-semibold text-gray-700 dark:text-gray-300">Initial Risks Identified</h4>
                <ul className="list-disc list-inside space-y-2 mt-1 text-sm text-gray-600 dark:text-gray-400">
                    {impactAssessment.initialRisks.map(risk => (
                        <li key={risk.title}><span className="font-medium">{risk.title}:</span> {risk.detail}</li>
                    ))}
                </ul>
            </div>
             <div>
                <h4 className="font-semibold text-gray-700 dark:text-gray-300">Mitigation Strategies</h4>
                <ul className="list-disc list-inside space-y-2 mt-1 text-sm text-gray-600 dark:text-gray-400">
                     {impactAssessment.mitigations.map(mitigation => (
                        <li key={mitigation.title}><span className="font-medium">{mitigation.title}:</span> {mitigation.detail}</li>
                    ))}
                </ul>
            </div>
        </div>
      </div>
    </div>
  );
};
