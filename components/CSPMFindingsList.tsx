

import React, { useState, useMemo } from 'react';
import { CSPMFinding, CSPMFindingSeverity, CloudProvider } from '../types';
import { BotIcon, FilterIcon } from './icons';

interface CSPMFindingsListProps {
  findings: CSPMFinding[];
  onSelectFinding: (finding: CSPMFinding) => void;
}

const severityClasses: Record<CSPMFindingSeverity, string> = {
  Critical: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
  High: 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300',
  Medium: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
  Low: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
  Informational: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
};

const providerOptions: (CloudProvider | 'All')[] = ['All', 'AWS', 'GCP', 'Azure'];
const severityOptions: (CSPMFindingSeverity | 'All')[] = ['All', 'Critical', 'High', 'Medium', 'Low', 'Informational'];

export const CSPMFindingsList: React.FC<CSPMFindingsListProps> = ({ findings, onSelectFinding }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [providerFilter, setProviderFilter] = useState<CloudProvider | 'All'>('All');
  const [severityFilter, setSeverityFilter] = useState<CSPMFindingSeverity | 'All'>('All');

  const filteredFindings = useMemo(() => {
    return findings.filter(finding => {
      const providerMatch = providerFilter === 'All' || finding.provider === providerFilter;
      const severityMatch = severityFilter === 'All' || finding.severity === severityFilter;
      const searchMatch = (
        finding.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
        finding.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
        finding.resourceId.toLowerCase().includes(searchTerm.toLowerCase())
      );
      return providerMatch && severityMatch && searchMatch;
    });
  }, [findings, searchTerm, providerFilter, severityFilter]);

  return (
    <div>
      <div className="p-4 flex flex-col md:flex-row gap-4">
        <div className="flex-grow">
          <input
            type="text"
            placeholder="Search findings..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
          />
        </div>
        <div className="flex-shrink-0 w-full md:w-40">
          <select value={providerFilter} onChange={(e) => setProviderFilter(e.target.value as CloudProvider | 'All')} className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm">
            {providerOptions.map(opt => <option key={opt} value={opt}>{opt === 'All' ? 'All Providers' : opt}</option>)}
          </select>
        </div>
        <div className="flex-shrink-0 w-full md:w-40">
          <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value as CSPMFindingSeverity | 'All')} className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm">
            {severityOptions.map(opt => <option key={opt} value={opt}>{opt === 'All' ? 'All Severities' : opt}</option>)}
          </select>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
          <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
            <tr>
              <th scope="col" className="px-6 py-3">Finding</th>
              <th scope="col" className="px-6 py-3">Severity</th>
              <th scope="col" className="px-6 py-3">Provider</th>
              <th scope="col" className="px-6 py-3">Last Seen</th>
              <th scope="col" className="px-6 py-3">Action</th>
            </tr>
          </thead>
          <tbody>
            {filteredFindings.map(finding => (
              <tr key={finding.id} className="bg-white dark:bg-gray-800 border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50">
                <td className="px-6 py-4">
                  <p className="font-semibold text-gray-800 dark:text-gray-200">{finding.title}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 font-mono mt-1">{finding.resourceId}</p>
                </td>
                <td className="px-6 py-4">
                  <span className={`px-2 py-1 text-xs font-medium rounded-full ${severityClasses[finding.severity]}`}>
                    {finding.severity}
                  </span>
                </td>
                <td className="px-6 py-4">{finding.provider}</td>
                <td className="px-6 py-4">{new Date(finding.lastSeen).toLocaleDateString()}</td>
                <td className="px-6 py-4">
                  <button
                    onClick={() => onSelectFinding(finding)}
                    className="flex items-center text-xs font-medium text-primary-600 hover:text-primary-800 dark:text-primary-400 dark:hover:text-primary-200"
                  >
                    <BotIcon size={14} className="mr-1.5" />
                    AI Remediation
                  </button>
                </td>
              </tr>
            ))}
             {filteredFindings.length === 0 && (
                <tr>
                    <td colSpan={5} className="text-center py-8 text-gray-500 dark:text-gray-400">
                        No findings match your search criteria.
                    </td>
                </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
