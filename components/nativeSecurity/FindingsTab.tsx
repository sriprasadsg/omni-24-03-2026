import React, { useEffect, useState } from 'react';
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

export function FindingsTab() {
  const [findings, setFindings] = useState<SecurityFinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [agentId, setAgentId] = useState('');
  const [scanType, setScanType] = useState<'file' | 'vuln' | 'fim'>('file');
  const [target, setTarget] = useState('');
  const [triggering, setTriggering] = useState(false);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchFindings({ limit: 100 });
      setFindings(data);
    } catch (e: any) {
      setError(e?.message || 'Failed to load findings');
    } finally {
      setLoading(false);
    }
  }

  async function handleTriggerScan() {
    if (!agentId.trim()) {
      showToast('Agent ID is required to trigger a scan', 'error');
      return;
    }
    setTriggering(true);
    try {
      await triggerScan(agentId.trim(), scanType, target.trim() || undefined);
      showToast('Scan queued — findings will refresh shortly', 'success');
      // Verdicts return asynchronously once the agent reports back.
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
            className="bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-1.5 rounded-lg"
          >
            {triggering ? 'Queuing…' : 'Trigger Scan'}
          </button>
        </div>
      </div>

      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium">Findings Feed</h3>
          <span className="text-gray-400 text-xs">{findings.length}</span>
        </div>

        {loading && <p className="text-gray-400 text-sm">Loading findings…</p>}
        {error && !loading && <p className="text-red-400 text-sm">{error}</p>}
        {!loading && !error && findings.length === 0 && (
          <p className="text-gray-500 text-xs italic">No findings — the fleet is clean.</p>
        )}

        {!loading && !error && findings.length > 0 && (
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
                {findings.map((f, i) => (
                  <tr key={i} className="border-b border-gray-800">
                    <td className="py-2 pr-4 text-gray-300 capitalize">{f.source}</td>
                    <td className="py-2 pr-4">
                      <span className={`text-xs px-2 py-0.5 rounded border ${SEVERITY_COLOR[f.severity] || SEVERITY_COLOR.informational}`}>
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
        )}
      </div>
    </div>
  );
}
