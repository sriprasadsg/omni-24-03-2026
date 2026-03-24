
import React from 'react';
import { SecurityCase, CaseStatus } from '../types';
// FIX: Replaced non-existent BoxIcon and added BoxIcon to icons.tsx.
import { BoxIcon } from './icons';

interface CaseManagementProps {
  cases: SecurityCase[];
  onViewCase: (caseItem: SecurityCase) => void;
}

const statusColumns: CaseStatus[] = ['New', 'In Progress', 'On Hold', 'Resolved'];

const statusStyles: Record<CaseStatus, { bg: string; text: string; border: string }> = {
  New: { bg: 'bg-blue-50 dark:bg-blue-900/50', text: 'text-blue-800 dark:text-blue-300', border: 'border-blue-500' },
  'In Progress': { bg: 'bg-amber-50 dark:bg-amber-900/50', text: 'text-amber-800 dark:text-amber-300', border: 'border-amber-500' },
  'On Hold': { bg: 'bg-gray-100 dark:bg-gray-700/50', text: 'text-gray-800 dark:text-gray-300', border: 'border-gray-500' },
  Resolved: { bg: 'bg-green-50 dark:bg-green-900/50', text: 'text-green-800 dark:text-green-300', border: 'border-green-500' },
};

const CaseCard: React.FC<{ caseItem: SecurityCase; onClick: () => void }> = ({ caseItem, onClick }) => {
  const styles = statusStyles[caseItem.status];
  return (
    <button 
      onClick={onClick}
      className={`w-full text-left p-3 rounded-lg shadow-sm border ${styles.bg} border-gray-200 dark:border-gray-700 hover:shadow-md hover:ring-2 hover:ring-primary-500 transition-all focus:outline-none focus:ring-2 focus:ring-primary-500`}
    >
      <div className="flex justify-between items-start">
        <p className="font-semibold text-sm text-gray-800 dark:text-gray-200">{caseItem.title}</p>
        <span className={`text-xs font-bold ${styles.text}`}>{caseItem.id}</span>
      </div>
      <div className="mt-2 text-xs text-gray-500 dark:text-gray-400 space-y-1">
        <p>Severity: <span className="font-medium">{caseItem.severity}</span></p>
        <p>Owner: <span className="font-medium">{caseItem.owner || 'Unassigned'}</span></p>
        <p>Last Update: {new Date(caseItem.updatedAt).toLocaleDateString()}</p>
      </div>
    </button>
  );
};

export const CaseManagement: React.FC<CaseManagementProps> = ({ cases, onViewCase }) => {
  return (
    <div className="w-full">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {statusColumns.map(status => (
          <div key={status} className="bg-gray-100 dark:bg-gray-900/50 rounded-lg">
            <h3 className={`p-3 text-sm font-semibold border-b-2 ${statusStyles[status].border} ${statusStyles[status].text}`}>
              {status} ({cases.filter(c => c.status === status).length})
            </h3>
            <div className="p-3 space-y-3 max-h-[60vh] overflow-y-auto">
              {cases.filter(c => c.status === status).map(caseItem => (
                <CaseCard key={caseItem.id} caseItem={caseItem} onClick={() => onViewCase(caseItem)} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
