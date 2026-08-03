import React, { useEffect, useState } from 'react';
import { fetchRemediationAudit } from '../../services/apiService';
import { RemediationAuditEntry } from '../../types';

const STAGE_COLOR: Record<string, string> = {
  resolved: 'text-emerald-400',
  verified: 'text-emerald-400',
  failed: 'text-red-400',
  escalated: 'text-red-400',
  rollback_dispatched: 'text-orange-400',
  override_denied: 'text-red-400',
  override_approved: 'text-cyan-400',
  pending_approval: 'text-yellow-400',
  dispatched: 'text-cyan-400',
  deferred: 'text-gray-400',
};

export function AuditTab() {
  const [entries, setEntries] = useState<RemediationAuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchRemediationAudit({ limit: 100 });
      setEntries(data);
    } catch (e: any) {
      setError(e?.message || 'Failed to load audit trail');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium">Immutable Audit Trail</h3>
        <button onClick={load} className="text-gray-400 hover:text-white text-xs">Refresh</button>
      </div>

      {loading && <p className="text-gray-400 text-sm">Loading audit trail…</p>}
      {error && !loading && <p className="text-red-400 text-sm">{error}</p>}
      {!loading && !error && entries.length === 0 && (
        <p className="text-gray-500 text-xs italic">No remediation activity yet.</p>
      )}

      {!loading && !error && entries.length > 0 && (
        <div className="space-y-2">
          {entries.map((e, i) => (
            <div key={i} className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <span className={`text-xs font-medium ${STAGE_COLOR[e.stage] || 'text-gray-300'}`}>
                  {e.stage}
                </span>
                <span className="text-gray-500 text-xs">{e.ts}</span>
              </div>
              <div className="mt-1 text-xs text-gray-400 flex flex-wrap gap-x-4 gap-y-0.5">
                <span>Remediation: <span className="text-gray-300">{e.remediation_id}</span></span>
                {e.playbook && <span>Playbook: <span className="text-gray-300">{e.playbook}</span></span>}
                {e.finding && <span>Finding: <span className="text-gray-300">{e.finding.type}/{e.finding.severity}</span></span>}
                {e.approver && <span>By: <span className="text-gray-300">{e.approver}</span></span>}
                {e.verification_result && <span>Result: <span className="text-gray-300">{e.verification_result}</span></span>}
                {e.reason && <span>Reason: <span className="text-gray-300">{e.reason}</span></span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
