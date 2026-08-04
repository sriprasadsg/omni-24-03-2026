import React, { useEffect, useState, useCallback } from 'react';
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

const STAGES = Object.keys(STAGE_COLOR);

export function AuditTab() {
  const [entries, setEntries] = useState<RemediationAuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [stageFilter, setStageFilter] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [totalCount, setTotalCount] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchRemediationAudit({ limit: pageSize, offset: (page - 1) * pageSize });
      setEntries(data);
      setTotalCount(data.length + (page - 1) * pageSize);
    } catch (e: any) {
      setError(e?.message || 'Failed to load audit trail');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize]);

  useEffect(() => { load(); }, [load]);

  const filteredEntries = entries.filter((e) => {
    if (stageFilter !== 'all' && e.stage !== stageFilter) return false;
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      return (
        e.remediation_id?.toLowerCase().includes(term) ||
        e.playbook?.toLowerCase().includes(term) ||
        e.approver?.toLowerCase().includes(term) ||
        e.reason?.toLowerCase().includes(term)
      );
    }
    return true;
  });

  const totalPages = Math.ceil(totalCount / pageSize);

  return (
    <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <h3 className="text-sm font-medium">Immutable Audit Trail</h3>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="search"
            className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white w-64"
            placeholder="Search remediation, playbook, approver…"
            value={searchTerm}
            onChange={(e) => { setSearchTerm(e.target.value); setPage(1); }}
            aria-label="Search audit trail"
          />
          <select
            className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white"
            value={stageFilter}
            onChange={(e) => { setStageFilter(e.target.value); setPage(1); }}
            aria-label="Filter by stage"
          >
            <option value="all">All Stages</option>
            {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <button onClick={load} className="text-gray-400 hover:text-white text-xs px-2 py-1">Refresh</button>
        </div>
      </div>

      {loading && <p className="text-gray-400 text-sm">Loading audit trail…</p>}
      {error && !loading && <p className="text-red-400 text-sm">{error}</p>}
      {!loading && !error && entries.length === 0 && (
        <p className="text-gray-500 text-xs italic">No remediation activity yet</p>
      )}

      {!loading && !error && entries.length > 0 && (
        <>
          <div className="space-y-2">
            {filteredEntries.map((e, i) => (
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

          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-700">
              <span className="text-xs text-gray-400">
                Page {page} of {totalPages} · {totalCount} total
              </span>
              <div className="flex gap-1">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white text-xs px-2 py-1 rounded"
                  aria-label="Previous page"
                >
                  Prev
                </button>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white text-xs px-2 py-1 rounded"
                  aria-label="Next page"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}