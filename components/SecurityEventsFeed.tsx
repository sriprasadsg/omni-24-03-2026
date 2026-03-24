



import React, { useState } from 'react';
import { SecurityEvent, AlertSeverity } from '../types';
import { AiInsights } from './AiInsights';
import { BotIcon, FileCodeIcon, ShieldSearchIcon } from './icons';
import { useUser } from '../contexts/UserContext';
import { useTimeZone } from '../contexts/TimeZoneContext';

interface SecurityEventsFeedProps {
  events: SecurityEvent[];
  onScanArtifact: (event: SecurityEvent, artifact: string, type: 'ip' | 'hash' | 'domain') => void;
}

const severityClasses: Record<AlertSeverity, { bg: string; text: string; ring: string }> = {
  Critical: { bg: 'bg-red-100 dark:bg-red-900/50', text: 'text-red-800 dark:text-red-300', ring: 'ring-red-500/20' },
  High: { bg: 'bg-orange-100 dark:bg-orange-900/50', text: 'text-orange-800 dark:text-orange-300', ring: 'ring-orange-500/20' },
  Medium: { bg: 'bg-amber-100 dark:bg-amber-900/50', text: 'text-amber-800 dark:text-amber-300', ring: 'ring-amber-500/20' },
  Low: { bg: 'bg-blue-100 dark:bg-blue-900/50', text: 'text-blue-800 dark:text-blue-300', ring: 'ring-blue-500/20' },
};

export const SecurityEventsFeed: React.FC<SecurityEventsFeedProps> = ({ events, onScanArtifact }) => {
  const { timeZone } = useTimeZone();
  const [selectedEvent, setSelectedEvent] = useState<SecurityEvent | null>(events[0] || null);
  const { hasPermission } = useUser();
  const canManageCases = hasPermission('manage:security_cases');
  const canManagePlaybooks = hasPermission('manage:security_playbooks');
  const canInvestigate = hasPermission('investigate:security');

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
      <div className="max-h-[350px] overflow-y-auto pr-2">
        <div className="space-y-3">
          {events.map(event => (
            <div
              key={event.id}
              onClick={() => setSelectedEvent(event)}
              className={`p-3 rounded-lg cursor-pointer transition-all ${selectedEvent?.id === event.id
                ? 'ring-2 ring-primary-500 bg-primary-50 dark:bg-primary-900/30'
                : 'bg-gray-50 dark:bg-gray-800/50 hover:bg-gray-100 dark:hover:bg-gray-700/50'
                }`}
            >
              <div className="flex justify-between items-start">
                <div>
                  <p className="font-semibold text-gray-800 dark:text-gray-200">{event.description}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    {new Date(event.timestamp).toLocaleString(undefined, { timeZone })} | Host: {event.source.hostname}
                  </p>
                </div>
                <span className={`ml-4 flex-shrink-0 px-2 py-1 text-xs font-medium rounded-full ring-1 ring-inset ${severityClasses[event.severity].bg} ${severityClasses[event.severity].text} ${severityClasses[event.severity].ring}`}>
                  {event.severity}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div>
        {selectedEvent ? (
          <div className="space-y-4">
            <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
              <h3 className="font-semibold mb-2">Event Details</h3>
              <div className="text-sm space-y-2">
                <p><span className="font-medium text-gray-600 dark:text-gray-400">Description:</span> {selectedEvent.description}</p>
                <p><span className="font-medium text-gray-600 dark:text-gray-400">Type:</span> {selectedEvent.type}</p>
                <div className="flex items-center justify-between">
                  <p><span className="font-medium text-gray-600 dark:text-gray-400">Source IP:</span> <span className="font-mono text-xs">{selectedEvent.source.ip}</span></p>
                  <button
                    onClick={() => onScanArtifact(selectedEvent, selectedEvent.source.ip, 'ip')}
                    disabled={!canInvestigate}
                    title="Scan with VirusTotal"
                    className="flex items-center text-xs font-medium text-primary-600 hover:text-primary-800 dark:text-primary-400 dark:hover:text-primary-200 disabled:text-gray-400 dark:disabled:text-gray-500 disabled:cursor-not-allowed disabled:hover:no-underline">
                    <ShieldSearchIcon size={14} className="mr-1.5" />
                    Scan IP
                  </button>
                </div>
                {selectedEvent.mitreAttack && (
                  <p><span className="font-medium text-gray-600 dark:text-gray-400">MITRE ATT&CK:</span> <a href={selectedEvent.mitreAttack.url} target="_blank" rel="noopener noreferrer" className="text-primary-600 dark:text-primary-400 hover:underline">{selectedEvent.mitreAttack.technique}</a></p>
                )}
                {selectedEvent.details && (
                  <div className="pt-2">
                    <h4 className="font-medium text-gray-600 dark:text-gray-400 mb-1">Raw Details</h4>
                    {selectedEvent.details.fileHash && (
                      <div className="flex items-center justify-between mb-2">
                        <p><span className="font-medium text-gray-600 dark:text-gray-400">File Hash:</span> <span className="font-mono text-xs">{selectedEvent.details.fileHash}</span></p>
                        <button
                          onClick={() => onScanArtifact(selectedEvent, selectedEvent.details.fileHash, 'hash')}
                          disabled={!canInvestigate}
                          title="Scan with VirusTotal"
                          className="flex items-center text-xs font-medium text-primary-600 hover:text-primary-800 dark:text-primary-400 dark:hover:text-primary-200 disabled:text-gray-400 dark:disabled:text-gray-500 disabled:cursor-not-allowed disabled:hover:no-underline">
                          <ShieldSearchIcon size={14} className="mr-1.5" />
                          Scan Hash
                        </button>
                      </div>
                    )}
                    <pre className="p-2 bg-gray-900 dark:bg-black rounded-md text-xs text-gray-300 whitespace-pre-wrap">
                      {JSON.stringify(selectedEvent.details, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            </div>
            <div className="flex space-x-2">
              <button
                className="flex-1 px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
                disabled={!canManageCases}
                title={!canManageCases ? "You don't have permission to create cases" : "Create a new case from this event"}
              >
                Create Case
              </button>
              <button
                className="flex-1 px-4 py-2 text-sm font-medium text-primary-700 bg-primary-100 rounded-lg hover:bg-primary-200 dark:bg-primary-900/50 dark:text-primary-300 dark:hover:bg-primary-900 disabled:bg-gray-300 disabled:text-gray-500 disabled:cursor-not-allowed"
                disabled={!canManagePlaybooks}
                title={!canManagePlaybooks ? "You don't have permission to run playbooks" : "Run an automation playbook"}
              >
                Run Playbook
              </button>
            </div>
          </div>
        ) : (
          <div className="h-full flex items-center justify-center bg-gray-50 dark:bg-gray-800/50 rounded-lg">
            <p className="text-sm text-gray-500 dark:text-gray-400">Select an event to view details</p>
          </div>
        )}
      </div>
    </div>
  );
};
