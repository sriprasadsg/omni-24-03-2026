import React from 'react';
import { SecurityCase, CaseStatus } from '../types';
import { BoxIcon, UserIcon } from './icons';

interface CaseManagementProps {
  cases: SecurityCase[];
  onViewCase: (caseItem: SecurityCase) => void;
}

const statusColumns: CaseStatus[] = ['New', 'In Progress', 'On Hold', 'Resolved'];

const statusDots: Record<CaseStatus, string> = {
  New: 'bg-blue-500',
  'In Progress': 'bg-amber-500',
  'On Hold': 'bg-gray-400',
  Resolved: 'bg-emerald-500',
};

const severityPills: Record<string, string> = {
  Critical: 'text-red-700 dark:text-red-300 bg-red-500/10 ring-red-500/20',
  High: 'text-orange-700 dark:text-orange-300 bg-orange-500/10 ring-orange-500/20',
  Medium: 'text-amber-700 dark:text-amber-300 bg-amber-500/10 ring-amber-500/20',
  Low: 'text-blue-700 dark:text-blue-300 bg-blue-500/10 ring-blue-500/20',
};

const CaseCard: React.FC<{ caseItem: SecurityCase; onClick: () => void }> = ({ caseItem, onClick }) => (
  <button
    onClick={onClick}
    className="w-full text-left p-3.5 rounded-xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-sm hover:border-primary-500/40 hover:shadow-card transition-all"
  >
    <div className="flex items-start justify-between gap-2">
      <p className="font-semibold text-sm text-gray-900 dark:text-gray-100 line-clamp-2">{caseItem.title}</p>
      <span className={`flex-shrink-0 px-1.5 py-px rounded-full text-[11px] font-semibold ring-1 ring-inset ${severityPills[caseItem.severity] || severityPills.Low}`}>{caseItem.severity}</span>
    </div>
    <p className="mt-1 font-mono text-[11px] text-gray-500 dark:text-gray-400 truncate">{caseItem.id}</p>
    <div className="mt-2.5 flex items-center justify-between gap-2 text-xs text-gray-500 dark:text-gray-400">
      <span className="flex items-center gap-1 min-w-0">
        <UserIcon size={12} className="flex-shrink-0" />
        <span className="truncate">{caseItem.owner || 'Unassigned'}</span>
      </span>
      <span className="flex-shrink-0 tabular-nums" title="Last update">{new Date(caseItem.updatedAt).toLocaleDateString()}</span>
    </div>
  </button>
);

export const CaseManagement: React.FC<CaseManagementProps> = ({ cases, onViewCase }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5">
      {statusColumns.map(status => {
        const columnCases = cases.filter(c => c.status === status);
        return (
          <section key={status} aria-label={`${status} cases`} className="rounded-2xl bg-gray-100/70 dark:bg-white/[0.03] ring-1 ring-inset ring-gray-200/70 dark:ring-white/[0.06] flex flex-col">
            <h3 className="px-4 pt-3.5 pb-2 flex items-center gap-2 text-[13px] font-semibold text-gray-800 dark:text-gray-200">
              <span className={`h-2 w-2 rounded-full ${statusDots[status]}`} aria-hidden="true" />
              {status}
              <span className="ml-auto px-1.5 py-px rounded-full text-[11px] font-semibold tabular-nums text-gray-600 dark:text-gray-300 bg-white dark:bg-white/[0.06] ring-1 ring-inset ring-gray-200/70 dark:ring-transparent">{columnCases.length}</span>
            </h3>
            <div className="px-3 pb-3 space-y-2.5 max-h-[60vh] overflow-y-auto">
              {columnCases.length === 0 ? (
                <div className="py-6 text-center text-xs text-gray-500 dark:text-gray-400">
                  <BoxIcon size={18} className="mx-auto mb-1.5 text-gray-400" />
                  No cases
                </div>
              ) : (
                columnCases.map(caseItem => (
                  <CaseCard key={caseItem.id} caseItem={caseItem} onClick={() => onViewCase(caseItem)} />
                ))
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
};
