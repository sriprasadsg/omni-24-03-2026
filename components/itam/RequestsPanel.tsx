import React, { useEffect, useState, useCallback } from 'react';
import Modal from '../ui/Modal';
import { ItamAssetRequest } from '../../types';
import { fetchAssetRequests, createAssetRequest, approveAssetRequest, rejectAssetRequest } from '../../services/apiService';
import { showToast } from '../../utils/toast';

const STATUS_STYLES: Record<string, string> = {
  pending: 'text-amber-400 bg-amber-900/20 border-amber-800',
  approved: 'text-green-500 bg-green-900/20 border-green-800',
  rejected: 'text-red-400 bg-red-900/20 border-red-800',
};

export function RequestsPanel() {
  const [requests, setRequests] = useState<ItamAssetRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState({ item_description: '', quantity: '1', reason: '' });
  const [actioningId, setActioningId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRequests(await fetchAssetRequests());
    } catch (e: any) {
      setError(e?.message || "Couldn't load asset requests");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleCreate() {
    if (!form.item_description.trim() || !form.reason.trim()) return;
    try {
      await createAssetRequest({
        item_description: form.item_description.trim(),
        quantity: Number(form.quantity) || 1,
        reason: form.reason.trim(),
      });
      showToast('Asset request submitted.', 'success');
      setAddOpen(false);
      setForm({ item_description: '', quantity: '1', reason: '' });
      load();
    } catch (e: any) {
      showToast(e?.message || "Couldn't submit asset request.", 'error');
    }
  }

  async function handleApprove(id: string) {
    setActioningId(id);
    try {
      await approveAssetRequest(id);
      showToast('Asset request approved.', 'success');
      load();
    } catch (e: any) {
      showToast(e?.message || 'Failed to approve request.', 'error');
    } finally {
      setActioningId(null);
    }
  }

  async function handleReject(id: string) {
    setActioningId(id);
    try {
      await rejectAssetRequest(id);
      showToast('Asset request rejected.', 'success');
      load();
    } catch (e: any) {
      showToast(e?.message || 'Failed to reject request.', 'error');
    } finally {
      setActioningId(null);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white">Asset Requests</h3>
        <button onClick={() => setAddOpen(true)} className="bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors">
          New Request
        </button>
      </div>
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
        {loading && <p className="text-gray-400 text-sm">Loading…</p>}
        {error && !loading && <p className="text-red-400 text-sm">{error}</p>}
        {!loading && !error && requests.length === 0 && (
          <div className="text-center py-8">
            <h3 className="text-sm font-semibold text-white mb-1">No asset requests yet</h3>
            <p className="text-gray-500 text-xs">Submit a request for a new asset to start the approval workflow.</p>
          </div>
        )}
        {!loading && !error && requests.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 text-xs border-b border-gray-700">
                <th className="py-2 pr-4">Item</th>
                <th className="py-2 pr-4">Qty</th>
                <th className="py-2 pr-4">Reason</th>
                <th className="py-2 pr-4">Requested</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 pr-4" />
              </tr>
            </thead>
            <tbody>
              {requests.map((r) => (
                <tr key={r.id} className="border-b border-gray-800">
                  <td className="py-2 pr-4 text-white font-medium">{r.item_description}</td>
                  <td className="py-2 pr-4 text-gray-300">{r.quantity}</td>
                  <td className="py-2 pr-4 text-gray-300 max-w-xs truncate" title={r.reason}>{r.reason}</td>
                  <td className="py-2 pr-4 text-gray-300">{r.request_date ? r.request_date.slice(0, 10) : '—'}</td>
                  <td className="py-2 pr-4">
                    <span className={`text-xs px-2 py-0.5 rounded border capitalize ${STATUS_STYLES[r.status] || ''}`}>
                      {r.status}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-right whitespace-nowrap">
                    {r.status === 'pending' && (
                      <>
                        <button
                          onClick={() => handleApprove(r.id)}
                          disabled={actioningId === r.id}
                          className="text-green-400 hover:text-green-300 text-xs font-medium mr-3 disabled:opacity-50"
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => handleReject(r.id)}
                          disabled={actioningId === r.id}
                          className="text-red-400 hover:text-red-300 text-xs font-medium disabled:opacity-50"
                        >
                          Reject
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Modal isOpen={addOpen} onClose={() => setAddOpen(false)} title="New Asset Request" confirmLabel="Submit" onConfirm={handleCreate}>
        <div className="space-y-3 mb-4">
          <input
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
            placeholder="Item description"
            value={form.item_description}
            onChange={(e) => setForm({ ...form, item_description: e.target.value })}
            aria-label="Item Description"
          />
          <input
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
            type="number"
            min={1}
            placeholder="Quantity"
            value={form.quantity}
            onChange={(e) => setForm({ ...form, quantity: e.target.value })}
            aria-label="Quantity"
          />
          <textarea
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
            placeholder="Reason for request"
            value={form.reason}
            onChange={(e) => setForm({ ...form, reason: e.target.value })}
            aria-label="Reason"
            rows={3}
          />
        </div>
      </Modal>
    </div>
  );
}
