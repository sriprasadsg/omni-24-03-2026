import React, { useState } from 'react';
import { SecurityEvent } from '../types';
import { ShieldSearchIcon, ActivityIcon, ExternalLinkIcon } from './icons';
import { useUser } from '../contexts/UserContext';
import { useTimeZone } from '../contexts/TimeZoneContext';

interface SecurityEventsFeedProps {
  events: SecurityEvent[];
  onScanArtifact: (event: SecurityEvent, artifact: string, type: 'ip' | 'hash' | 'domain') => void;
  onCreateCase?: (event: SecurityEvent) => void;
  onRunPlaybook?: (event: SecurityEvent) => void;
}

const severityPills: Record<string, string> = {
  Critical: 'text-red-700 dark:text-red-300 bg-red-500/10 ring-red-500/20',
  High: 'text-orange-700 dark:text-orange-300 bg-orange-500/10 ring-orange-500/20',
  Medium: 'text-amber-700 dark:text-amber-300 bg-amber-500/10 ring-amber-500/20',
  Low: 'text-blue-700 dark:text-blue-300 bg-blue-500/10 ring-blue-500/20',
};

// Agents report severity in any case ("critical", "HIGH").
const SeverityPill: React.FC<{ severity: string }> = ({ severity }) => {
  const s = severity ? severity.charAt(0).toUpperCase() + severity.slice(1).toLowerCase() : 'Low';
  return (
    <span className={`flex-shrink-0 px-2 py-0.5 rounded-full text-[11px] font-semibold ring-1 ring-inset ${severityPills[s] || severityPills.Low}`}>
      {severity}
    </span>
  );
};

const scanButton = 'flex-shrink-0 inline-flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-xs font-medium text-primary-700 dark:text-primary-300 ring-1 ring-inset ring-primary-500/25 hover:bg-primary-500/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-transparent';
const term = 'text-gray-500 dark:text-gray-400';

export const SecurityEventsFeed: React.FC<SecurityEventsFeedProps> = ({ events, onScanArtifact, onCreateCase, onRunPlaybook }) => {
  const { timeZone } = useTimeZone();
  // Track the id, not the object: events usually arrive after mount and are replaced on refresh.
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selectedEvent = events.find(e => e.id === selectedId) ?? events[0] ?? null;
  const { hasPermission } = useUser();
  const canManageCases = hasPermission('manage:security_cases');
  const canManagePlaybooks = hasPermission('manage:security_playbooks');
  const canInvestigate = hasPermission('investigate:security');

  const fileHash = typeof selectedEvent?.details?.fileHash === 'string' ? selectedEvent.details.fileHash : null;
  // fetchSecurityEvents fills a missing IP with 'N/A'.
  const sourceIp = selectedEvent?.source?.ip && selectedEvent.source.ip !== 'N/A' ? selectedEvent.source.ip : null;

  return (
    <section aria-label="Security events" className="h-full flex flex-col rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card overflow-hidden">
      <div className="px-5 pt-4 pb-3 border-b border-gray-100 dark:border-white/[0.06] flex items-center justify-between">
        <h3 className="text-[15px] font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <ActivityIcon size={16} className="text-primary-500" />
          Events
        </h3>
        <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold tabular-nums text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-white/[0.06]">{events.length}</span>
      </div>

      {events.length === 0 || !selectedEvent ? (
        <div className="flex-1 grid place-items-center p-8 text-center">
          <div>
            <ActivityIcon size={28} className="mx-auto text-gray-400" />
            <p className="mt-3 text-sm font-medium text-gray-700 dark:text-gray-300">No security events</p>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Events your agents raise appear here.</p>
          </div>
        </div>
      ) : (
        <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <ul className="p-2 space-y-1 overflow-y-auto max-h-[360px] lg:max-h-none border-b lg:border-b-0 lg:border-r border-gray-100 dark:border-white/[0.06]">
            {events.map(event => {
              const isSelected = event.id === selectedEvent.id;
              return (
                <li key={event.id} className="relative">
                  <button
                    type="button"
                    onClick={() => setSelectedId(event.id)}
                    aria-current={isSelected ? 'true' : undefined}
                    className={`w-full text-left pl-3.5 pr-3 py-3 rounded-xl transition-colors duration-150 ${isSelected
                      ? 'bg-primary-500/[0.08] ring-1 ring-inset ring-primary-500/30 dark:bg-primary-400/10'
                      : 'hover:bg-gray-100/80 dark:hover:bg-white/[0.04]'
                      }`}
                  >
                    {isSelected && <span className="absolute left-0 top-3 bottom-3 w-[3px] rounded-full bg-primary-500 dark:bg-primary-400" aria-hidden="true" />}
                    <div className="flex items-start justify-between gap-3 min-w-0">
                      <p className="font-semibold text-sm text-gray-900 dark:text-gray-100 line-clamp-2">{event.description}</p>
                      <SeverityPill severity={event.severity} />
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 flex items-center min-w-0">
                      <span className="truncate">{event.source?.hostname ?? 'Unknown host'}</span>
                      <span className="mx-1.5 text-gray-300 dark:text-gray-600">·</span>
                      <span className="flex-shrink-0 tabular-nums">
                        {new Date(event.timestamp).toLocaleString(undefined, { timeZone, month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </p>
                  </button>
                </li>
              );
            })}
          </ul>

          <div className="flex flex-col min-h-0">
            <div className="p-5 flex-1 overflow-y-auto">
              <div className="flex items-start justify-between gap-3">
                <h4 className="text-[15px] font-semibold text-gray-900 dark:text-white">{selectedEvent.description}</h4>
                <SeverityPill severity={selectedEvent.severity} />
              </div>
              <dl className="mt-4 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2.5 text-sm text-gray-800 dark:text-gray-200">
                <dt className={term}>Type</dt>
                <dd>{selectedEvent.type}</dd>
                <dt className={term}>Time</dt>
                <dd className="tabular-nums">{new Date(selectedEvent.timestamp).toLocaleString(undefined, { timeZone, dateStyle: 'medium', timeStyle: 'medium' })}</dd>
                <dt className={term}>Host</dt>
                <dd>{selectedEvent.source?.hostname ?? 'Unknown'}</dd>
                <dt className={`${term} self-center`}>Source IP</dt>
                <dd className="flex items-center justify-between gap-2 min-w-0">
                  <span className="font-mono text-[13px] truncate">{sourceIp ?? '—'}</span>
                  <button
                    onClick={() => sourceIp && onScanArtifact(selectedEvent, sourceIp, 'ip')}
                    disabled={!canInvestigate || !sourceIp}
                    title="Check this IP with VirusTotal"
                    className={scanButton}>
                    <ShieldSearchIcon size={13} />
                    Scan IP
                  </button>
                </dd>
                {selectedEvent.mitreAttack && (
                  <>
                    <dt className={term}>MITRE ATT&CK</dt>
                    <dd>
                      <a href={selectedEvent.mitreAttack.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary-700 dark:text-primary-300 hover:underline">
                        {selectedEvent.mitreAttack.technique}
                        <ExternalLinkIcon size={12} />
                      </a>
                    </dd>
                  </>
                )}
                {fileHash && (
                  <>
                    <dt className={`${term} self-center`}>File hash</dt>
                    <dd className="flex items-center justify-between gap-2 min-w-0">
                      <span className="font-mono text-xs truncate" title={fileHash}>{fileHash}</span>
                      <button
                        onClick={() => onScanArtifact(selectedEvent, fileHash, 'hash')}
                        disabled={!canInvestigate}
                        title="Check this file hash with VirusTotal"
                        className={scanButton}>
                        <ShieldSearchIcon size={13} />
                        Scan hash
                      </button>
                    </dd>
                  </>
                )}
              </dl>
              {selectedEvent.details && (
                <div className="mt-5">
                  <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">Raw details</p>
                  <pre className="p-3 rounded-xl bg-gray-950 text-gray-200 text-xs font-mono whitespace-pre-wrap break-all ring-1 ring-inset ring-white/[0.06] max-h-56 overflow-auto">
                    {JSON.stringify(selectedEvent.details, null, 2)}
                  </pre>
                </div>
              )}
            </div>
            <div className="px-5 py-3 border-t border-gray-100 dark:border-white/[0.06] flex gap-2">
              <button
                onClick={() => onCreateCase?.(selectedEvent)}
                className="flex-1 h-10 px-4 text-sm font-semibold text-white rounded-xl bg-primary-600 hover:bg-primary-700 transition-all active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={!canManageCases}
                title={!canManageCases ? "You don't have permission to create cases" : 'Open a case for this event'}
              >
                Create case
              </button>
              <button
                onClick={() => onRunPlaybook?.(selectedEvent)}
                className="flex-1 h-10 px-4 text-sm font-medium text-gray-700 dark:text-gray-200 glass rounded-xl transition-all hover:border-primary-500/40 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={!canManagePlaybooks}
                title={!canManagePlaybooks ? "You don't have permission to run playbooks" : 'Run an automation playbook'}
              >
                Run playbook
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
