import React, { useEffect, useState } from 'react';
import { fetchRemediationQueue, approveRemediation, denyRemediation } from '../../services/apiService';
import { RemediationQueueItem } from '../../types';
import { showToast } from '../../utils/toast';

export function RemediationQueueTab() {
  const [items, setItems] = useState<RemediationQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchRemediationQueue();
      setItems(data);
    } catch (e: any) {
      setError(e?.message || 'Failed to load remediation queue');
    } finally {
      setLoading(false);
    }
  }

  async function handleApprove(id: string) {
    setBusyId(id);
    try {
      await approveRemediation(id);
      showToast('Remediation approved — dispatching to the agent.', 'success');
      await load();
    } catch (e: any) {
      showToast(e?.message || 'Failed to approve remediation', 'error');
    } finally {
      setBusyId(null);
    }
  }

  async function handleDeny(id: string) {
    const reason = window.prompt('Reason for denying this remediation (optional):') || '';
    setBusyId(id);
    try {
      await denyRemediation(id, reason);
      showToast('Remediation denied.', 'success');
      await load();
    } catch (e: any) {
      showToast(e?.message || 'Failed to deny remediation', 'error');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium">Remediation Queue</h3>
        <span className="text-gray-400 text-xs">{items.length} pending / in flight</span>
      </div>

      {loading && <p className="text-gray-400 text-sm">Loading remediation queue…</p>}
      {error && !loading && <p className="text-red-400 text-sm">{error}</p>}
      {!loading && !error && items.length === 0 && (
        <p className="text-gray-500 text-xs italic">Nothing pending — the queue is clear.</p>
      )}

      {!loading && !error && items.length > 0 && (
        <div className="space-y-2">
          {items.map((item) => (
            <div key={item.id} className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 flex items-center justify-between flex-wrap gap-2">
              <div className="flex-1 min-w-[220px]">
                <p className="text-sm font-medium">
                  {item.playbookName} <span className="text-gray-500 font-normal">({item.findingType})</span>
                </p>
                <p className="text-gray-500 text-xs mt-0.5">
                  Agent {item.agentId || 'unknown'} · Finding {item.findingId} · {item.status}
                </p>
              </div>
              {item.status === 'pending_approval' ? (
                <div className="flex gap-2">
                  <button
                    onClick={() => handleApprove(item.id)}
                    disabled={busyId === item.id}
                    aria-label="Approve remediation"
                    className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-medium px-3 py-1.5 rounded-lg"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => handleDeny(item.id)}
                    disabled={busyId === item.id}
                    aria-label="Deny remediation"
                    className="bg-red-600/80 hover:bg-red-500 disabled:opacity-50 text-white text-xs font-medium px-3 py-1.5 rounded-lg"
                  >
                    Deny
                  </button>
                </div>
              ) : (
                <span className="text-xs text-gray-400 px-2 py-1">{item.status}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
