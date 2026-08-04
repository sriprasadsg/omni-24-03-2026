import React, { useEffect, useState, useCallback } from 'react';
import { fetchFindings, triggerScan } from '../../services/apiService';
import { SecurityFinding } from '../../types';
import { showToast } from '../../utils/toast';

const SEVERITY_COLOR: Record<string, string> = {
  critical: 'text-red-400 bg-red-900/30 border-red-800',
  high: 'text-orange-400 bg-orange-900/30 border-orange-800',
  medium: 'text-yellow-400 bg-yellow-900/30 border-yellow-800',
  low: 'text-blue-400 bg-blue-900/30 border-blue-800',
  informational: 'text-gray-400 bg-gray-800 border-gray-700',
};

const SEVERITIES = ['critical', 'high', 'medium', 'low', 'informational'] as const;
const SOURCES = ['scan', 'vulnerability', 'fim'] as const;

export function FindingsTab() {
  const [findings, setFindings] = useState<SecurityFinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [agentId, setAgentId] = useState('');
  const [scanType, setScanType] = useState<'file' | 'vuln' | 'fim'>('file');
  const [target, setTarget] = useState('');
  const [triggering, setTriggering] = useState(false);

  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [sourceFilter, setSourceFilter] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [totalCount, setTotalCount] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchFindings({ limit: pageSize, offset: (page - 1) * pageSize });
      setFindings(data);
      setTotalCount((prev) => prev + data.length);
    } catch (e: any) {
      setError(e?.message || 'Failed to load findings');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize]);

  useEffect(() => { load(); }, [load]);

  const filteredFindings = findings.filter((f) => {
    if (severityFilter !== 'all' && f.severity !== severityFilter) return false;
    if (sourceFilter !== 'all' && f.source !== sourceFilter) return false;
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      return (
        f.target?.toLowerCase().includes(term) ||
        f.hostname?.toLowerCase().includes(term) ||
        f.verdict_or_detail?.toLowerCase().includes(term)
      );
    }
    return true;
  });

  async function handleTriggerScan() {
    if (!agentId.trim()) {
      showToast('Agent ID is required to trigger a scan', 'error');
      return;
    }
    setTriggering(true);
    try {
      await triggerScan(agentId.trim(), scanType, target.trim() || undefined);
      showToast('Scan queued — findings will refresh shortly', 'success');
      setTimeout(load, 4000);
    } catch (e: any) {
      showToast(e?.message || 'Failed to trigger scan', 'error');
    } finally {
      setTriggering(false);
    }
  }

  return (
    <div>
      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 mb-4">
        <h3 className="text-sm font-medium mb-3">Scan Now</h3>
        <div className="flex flex-wrap gap-2 items-center">
          <input
            className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white flex-1 min-w-[160px]"
            placeholder="Agent ID"
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
          />
          <select
            className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white"
            value={scanType}
            onChange={(e) => setScanType(e.target.value as any)}
          >
            <option value="file">File</option>
            <option value="vuln">Vulnerability</option>
            <option value="fim">FIM</option>
          </select>
          <input
            className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white flex-1 min-w-[160px]"
            placeholder="Target (path / IP / hash / URL, optional)"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          />
          <button
            onClick={handleTriggerScan}
            disabled={triggering}
            className="bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-1.5 rounded-lg transition-colors"
            aria-label="Trigger scan"
          >
            {triggering ? 'Queuing…' : 'Trigger Scan'}
          </button>
        </div>
      </div>

      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <h3 className="text-sm font-medium">Findings Feed</h3>
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="search"
              className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white w-64"
              placeholder="Search target, host, detail…"
              value={searchTerm}
              onChange={(e) => { setSearchTerm(e.target.value); setPage(1); }}
              aria-label="Search findings"
            />
            <select
              className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white"
              value={severityFilter}
              onChange={(e) => { setSeverityFilter(e.target.value); setPage(1); }}
              aria-label="Filter by severity"
            >
              <option value="all">All Severities</option>
              {SEVERITIES.map((s) => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
            </select>
            <select
              className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white"
              value={sourceFilter}
              onChange={(e) => { setSourceFilter(e.target.value); setPage(1); }}
              aria-label="Filter by source"
            >
              <option value="all">All Sources</option>
              {SOURCES.map((s) => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
            </select>
          </div>
        </div>

        {loading && <p className="text-gray-400 text-sm">Loading findings…</p>}
        {error && !loading && <p className="text-red-400 text-sm">{error}</p>}
        {!loading && !error && findings.length === 0 && (
          <div className="text-center py-8">
            <p className="text-gray-500 text-xs italic mb-2">No findings — the fleet is clean.</p>
            <button
              onClick={handleTriggerScan}
              disabled={!agentId.trim() || triggering}
              className="bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-xs font-medium px-3 py-1 rounded"
              aria-label="Trigger First Scan"
            >
              Trigger First Scan
            </button>
          </div>
        )}

        {!loading && !error && findings.length > 0 && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 text-xs border-b border-gray-700">
                    <th className="py-2 pr-4">Source</th>
                    <th className="py-2 pr-4">Severity</th>
                    <th className="py-2 pr-4">Host</th>
                    <th className="py-2 pr-4">Target</th>
                    <th className="py-2 pr-4">Verdict / Detail</th>
                    <th className="py-2 pr-4">When</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredFindings.map((f, i) => (
                    <tr key={i} className="border-b border-gray-800">
                      <td className="py-2 pr-4 text-gray-300 capitalize">{f.source}</td>
                      <td className="py-2 pr-4">
                        <span
                          className={`text-xs px-2 py-0.5 rounded border ${SEVERITY_COLOR[f.severity] || SEVERITY_COLOR.informational}`}
                          role="img"
                          aria-label={`Severity ${f.severity}`}
                        >
                          {f.severity}
                        </span>
                      </td>
                      <td className="py-2 pr-4 text-gray-300">{f.hostname || '—'}</td>
                      <td className="py-2 pr-4 text-gray-400 max-w-[220px] truncate" title={f.target}>{f.target || '—'}</td>
                      <td className="py-2 pr-4 text-gray-400">{f.verdict_or_detail || '—'}</td>
                      <td className="py-2 pr-4 text-gray-500 text-xs whitespace-nowrap">{f.ts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
                    role="button"
                    aria-label="Previous page"
                  >
                    Prev
                  </button>
                  <button
                    onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                    className="bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white text-xs px-2 py-1 rounded"
                    role="button"
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
    </div>
  );
}