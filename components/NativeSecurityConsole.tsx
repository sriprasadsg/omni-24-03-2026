import React, { useState } from 'react';
import { FindingsTab } from './nativeSecurity/FindingsTab';
import { RemediationQueueTab } from './nativeSecurity/RemediationQueueTab';
import { PlaybooksTab } from './nativeSecurity/PlaybooksTab';
import { AuditTab } from './nativeSecurity/AuditTab';

type Tab = 'findings' | 'queue' | 'playbooks' | 'audit';

const TABS: { id: Tab; label: string }[] = [
  { id: 'findings', label: 'Findings' },
  { id: 'queue', label: 'Remediation Queue' },
  { id: 'playbooks', label: 'Playbooks' },
  { id: 'audit', label: 'Audit' },
];

// Operator console for the v3.4 native security scanning + autonomous
// remediation stack (Phases 50-53): scan/vuln/FIM findings feed, the
// approve/deny remediation queue, the deterministic playbook library, and
// the immutable audit trail. Server enforces the approval gate (53-04) —
// this UI only triggers/displays (D-05).
export function NativeSecurityConsole() {
  const [tab, setTab] = useState<Tab>('findings');

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Native Security Console</h1>
        <p className="text-gray-400 text-sm mt-1">
          Offline scan verdicts, local vulnerability findings, file-integrity drift, and the
          autonomous remediation queue — all agent-native, no external SIEM dependency.
        </p>
      </div>

      <div className="flex gap-1 mb-4 border-b border-gray-700">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.id
                ? 'border-cyan-500 text-white'
                : 'border-transparent text-gray-400 hover:text-gray-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'findings' && <FindingsTab />}
      {tab === 'queue' && <RemediationQueueTab />}
      {tab === 'playbooks' && <PlaybooksTab />}
      {tab === 'audit' && <AuditTab />}
    </div>
  );
}
