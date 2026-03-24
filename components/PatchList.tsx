import React, { useState, useMemo } from 'react';
import { Patch, PatchSeverity, PatchStatus } from '../types';
import { useUser } from '../contexts/UserContext';
import { EnrichedPatchModal } from './EnrichedPatchModal';

interface PatchListProps {
  patches: Patch[];
  selectedPatchIds: Set<string>;
  onSetSelectedPatchIds: React.Dispatch<React.SetStateAction<Set<string>>>;
}

const severityClasses: Record<PatchSeverity, string> = {
  Critical: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
  High: 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300',
  Medium: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
  Low: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
};

const statusClasses: Record<PatchStatus, string> = {
  Pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300',
  Deployed: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
  Failed: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
  Superseded: 'bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
};

const getCVSSColor = (score: number | undefined) => {
  if (!score) return 'text-gray-500';
  if (score >= 9.0) return 'text-red-600 dark:text-red-400 font-bold';
  if (score >= 7.0) return 'text-orange-600 dark:text-orange-400 font-bold';
  if (score >= 4.0) return 'text-yellow-600 dark:text-yellow-400 font-semibold';
  return 'text-blue-600 dark:text-blue-400';
};

const getPriorityColor = (score: number | undefined) => {
  if (!score) return 'text-gray-500';
  if (score >= 80) return 'text-red-600 dark:text-red-400 font-bold';
  if (score >= 60) return 'text-orange-600 dark:text-orange-400 font-bold';
  if (score >= 40) return 'text-yellow-600 dark:text-yellow-400 font-semibold';
  return 'text-blue-600 dark:text-blue-400';
};

const severityOptions: (PatchSeverity | 'All')[] = ['All', 'Critical', 'High', 'Medium', 'Low'];
const statusOptions: (PatchStatus | 'All')[] = ['All', 'Pending', 'Deployed', 'Failed', 'Superseded'];


export const PatchList: React.FC<PatchListProps> = ({ patches, selectedPatchIds, onSetSelectedPatchIds }) => {
  const { hasPermission } = useUser();
  const canManagePatches = hasPermission('manage:patches');

  const [searchTerm, setSearchTerm] = useState('');
  const [severityFilter, setSeverityFilter] = useState<PatchSeverity | 'All'>('All');
  const [statusFilter, setStatusFilter] = useState<PatchStatus | 'All'>('All');
  const [selectedPatch, setSelectedPatch] = useState<Patch | null>(null);

  const filteredPatches = useMemo(() => {
    return patches.filter(patch => {
      const severityMatch = severityFilter === 'All' || patch.severity === severityFilter;
      const statusMatch = statusFilter === 'All' || patch.status === statusFilter;
      const searchMatch = (
        (patch.cveId || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
        (patch.description || '').toLowerCase().includes(searchTerm.toLowerCase())
      );
      return severityMatch && statusMatch && searchMatch;
    });
  }, [patches, searchTerm, severityFilter, statusFilter]);

  const pendingPatches = useMemo(() => {
    return filteredPatches.filter(p => p.status === 'Pending');
  }, [filteredPatches]);

  const handleToggleSelection = (patchId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    onSetSelectedPatchIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(patchId)) {
        newSet.delete(patchId);
      } else {
        newSet.add(patchId);
      }
      return newSet;
    });
  };

  const handleToggleAll = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      onSetSelectedPatchIds(new Set(pendingPatches.map(p => p.id)));
    } else {
      onSetSelectedPatchIds(new Set());
    }
  };

  const handleRowClick = (patch: Patch) => {
    setSelectedPatch(patch);
  };

  const allPendingSelected = pendingPatches.length > 0 && pendingPatches.every(p => selectedPatchIds.has(p.id));

  return (
    <div>
      <div className="p-4 flex flex-col md:flex-row gap-4">
        <div className="flex-grow">
          <input
            type="text"
            placeholder="Search by CVE or description..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
          />
        </div>
        <div className="flex-shrink-0 w-full md:w-40">
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value as PatchSeverity | 'All')}
            className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
          >
            {severityOptions.map(opt => <option key={opt} value={opt}>{opt === 'All' ? 'All Severities' : opt}</option>)}
          </select>
        </div>
        <div className="flex-shrink-0 w-full md:w-40">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as PatchStatus | 'All')}
            className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
          >
            {statusOptions.map(opt => <option key={opt} value={opt}>{opt === 'All' ? 'All Statuses' : opt}</option>)}
          </select>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
          <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
            <tr>
              {canManagePatches && (
                <th scope="col" className="p-4">
                  <div className="flex items-center">
                    <input id="checkbox-all" type="checkbox" checked={allPendingSelected} onChange={handleToggleAll} className="w-4 h-4 text-primary-600 bg-gray-100 border-gray-300 rounded focus:ring-primary-500" />
                    <label htmlFor="checkbox-all" className="sr-only">checkbox</label>
                  </div>
                </th>
              )}
              <th scope="col" className="px-6 py-3">CVE ID</th>
              <th scope="col" className="px-6 py-3">Description</th>
              <th scope="col" className="px-6 py-3">Severity</th>
              <th scope="col" className="px-6 py-3">CVSS</th>
              <th scope="col" className="px-6 py-3">EPSS %</th>
              <th scope="col" className="px-6 py-3">Priority</th>
              <th scope="col" className="px-6 py-3">Status</th>
              <th scope="col" className="px-6 py-3">Assets</th>
            </tr>
          </thead>
          <tbody>
            {filteredPatches.map(patch => (
              <tr
                key={patch.id}
                onClick={() => handleRowClick(patch)}
                className="bg-white dark:bg-gray-800 border-b dark:border-gray-700 hover:bg-primary-50 dark:hover:bg-primary-900/20 cursor-pointer transition-colors"
              >
                {canManagePatches && (
                  <td className="w-4 p-4" onClick={(e) => e.stopPropagation()}>
                    {patch.status === 'Pending' && (
                      <div className="flex items-center">
                        <input
                          id={`checkbox-${patch.id}`}
                          type="checkbox"
                          checked={selectedPatchIds.has(patch.id)}
                          onChange={(e) => handleToggleSelection(patch.id, e as any)}
                          className="w-4 h-4 text-primary-600 bg-gray-100 border-gray-300 rounded focus:ring-primary-500"
                        />
                        <label htmlFor={`checkbox-${patch.id}`} className="sr-only">checkbox</label>
                      </div>
                    )}
                  </td>
                )}
                <td className="px-6 py-4">
                  <span className="font-mono text-xs font-bold text-primary-600 dark:text-primary-400">{patch.cveId}</span>
                </td>
                <td className="px-6 py-4 max-w-xs truncate text-gray-900 dark:text-gray-100">{patch.description}</td>
                <td className="px-6 py-4">
                  <span className={`px-2 py-1 text-xs font-medium rounded-full ${severityClasses[patch.severity] || 'bg-gray-100 text-gray-800'}`}>
                    {patch.severity}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <span className={`text-sm font-semibold ${getCVSSColor((patch as any).cvss_score)}`}>
                    {(patch as any).cvss_score ? (patch as any).cvss_score.toFixed(1) : 'N/A'}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <span className={`text-sm font-semibold ${(patch as any).epss_score && (patch as any).epss_score > 0.5 ? 'text-orange-600 dark:text-orange-400' : 'text-gray-600 dark:text-gray-400'}`}>
                    {(patch as any).epss_score ? ((patch as any).epss_score * 100).toFixed(1) + '%' : 'N/A'}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <span className={`text-sm font-bold ${getPriorityColor((patch as any).priority_score)}`}>
                    {(patch as any).priority_score ? Math.round((patch as any).priority_score) : 'N/A'}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <span className={`px-2 py-1 text-xs font-medium rounded-full ${statusClasses[patch.status] || 'bg-gray-100 text-gray-800'}`}>
                    {patch.status}
                  </span>
                </td>
                <td className="px-6 py-4 font-semibold text-center text-gray-900 dark:text-gray-100">{patch.affectedAssets?.length || 0}</td>
              </tr>
            ))}
            {filteredPatches.length === 0 && (
              <tr>
                <td colSpan={canManagePatches ? 10 : 9} className="text-center py-8 text-gray-500 dark:text-gray-400">
                  No patches match your search criteria.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {selectedPatch && (
        <EnrichedPatchModal
          isOpen={true}
          onClose={() => setSelectedPatch(null)}
          patch={selectedPatch}
        />
      )}
    </div>
  );
};
