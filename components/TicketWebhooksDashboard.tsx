import React, { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../services/apiService';

interface Webhook {
  id: string;
  url: string;
  events: string[];
  secret?: string;
  last_triggered?: string;
  failure_count?: number;
}

const ALL_EVENTS = [
  'ticket.created',
  'ticket.updated',
  'ticket.status_changed',
  'ticket.commented',
  'ticket.escalated',
  'ticket.resolved',
];

const defaultForm = { url: '', events: [] as string[], secret: '' };

const TicketWebhooksDashboard: React.FC = () => {
  const [webhooks, setWebhooks] = useState<Webhook[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState(defaultForm);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch('/api/tickets/webhooks');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setWebhooks(Array.isArray(data) ? data : (data.webhooks ?? []));
    } catch (e: any) {
      setError(e.message || 'Failed to load webhooks');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggleEvent = (ev: string) => {
    setForm(f => ({
      ...f,
      events: f.events.includes(ev) ? f.events.filter(e => e !== ev) : [...f.events, ev],
    }));
  };

  const handleAdd = async () => {
    if (!form.url.trim() || form.events.length === 0) return;
    setSaving(true);
    setSaveError(null);
    try {
      const body: Record<string, unknown> = { url: form.url.trim(), events: form.events };
      if (form.secret.trim()) body.secret = form.secret.trim();
      const res = await authFetch('/api/tickets/webhooks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setShowAdd(false);
      setForm(defaultForm);
      await load();
    } catch (e: any) {
      setSaveError(e.message || 'Failed to create webhook');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    setDeletingId(id);
    try {
      await authFetch(`/api/tickets/webhooks/${id}`, { method: 'DELETE' });
      setWebhooks(w => w.filter(wh => wh.id !== id));
    } catch {
      // silent fail — keep in list
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="bg-gray-900 min-h-screen text-white p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Ticket Webhooks</h1>
          <p className="text-gray-400 text-sm mt-1">Configure outbound webhooks for ticket lifecycle events</p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          + Add Webhook
        </button>
      </div>

      {loading ? (
        <div className="text-gray-400 py-8 text-center">Loading webhooks…</div>
      ) : error ? (
        <div className="text-red-400 py-8 text-center">{error}</div>
      ) : webhooks.length === 0 ? (
        <div className="text-gray-500 py-8 text-center">No webhooks configured.</div>
      ) : (
        <div className="space-y-3">
          {webhooks.map(wh => (
            <div key={wh.id} className="bg-gray-800 border border-gray-700 rounded-xl p-4 flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <p className="text-white font-mono text-sm truncate">{wh.url}</p>
                <div className="flex flex-wrap gap-1 mt-2">
                  {(wh.events ?? []).map(ev => (
                    <span key={ev} className="bg-blue-900/40 text-blue-300 border border-blue-700/40 px-2 py-0.5 rounded text-xs">{ev}</span>
                  ))}
                </div>
                <div className="flex gap-4 mt-2 text-xs text-gray-400">
                  {wh.last_triggered && (
                    <span>Last triggered: {new Date(wh.last_triggered).toLocaleString()}</span>
                  )}
                  {wh.failure_count !== undefined && wh.failure_count > 0 && (
                    <span className="text-red-400">Failures: {wh.failure_count}</span>
                  )}
                </div>
              </div>
              <button
                onClick={() => handleDelete(wh.id)}
                disabled={deletingId === wh.id}
                className="flex-shrink-0 text-red-400 hover:text-red-300 disabled:opacity-50 text-sm transition-colors px-2 py-1 rounded hover:bg-red-900/20"
              >
                {deletingId === wh.id ? '…' : 'Delete'}
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Add Webhook Modal */}
      {showAdd && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
          <div className="bg-gray-800 border border-gray-700 rounded-xl w-full max-w-md p-6">
            <h2 className="text-lg font-bold text-white mb-4">Add Webhook</h2>
            <div className="space-y-3">
              <input
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                placeholder="Endpoint URL *"
                value={form.url}
                onChange={e => setForm(f => ({ ...f, url: e.target.value }))}
              />
              <div>
                <p className="text-xs text-gray-400 mb-2">Events *</p>
                <div className="space-y-2">
                  {ALL_EVENTS.map(ev => (
                    <label key={ev} className="flex items-center gap-2 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={form.events.includes(ev)}
                        onChange={() => toggleEvent(ev)}
                        className="rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500"
                      />
                      <span className="text-sm text-gray-300 group-hover:text-white transition-colors">{ev}</span>
                    </label>
                  ))}
                </div>
              </div>
              <input
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                placeholder="Secret (optional)"
                value={form.secret}
                onChange={e => setForm(f => ({ ...f, secret: e.target.value }))}
              />
            </div>
            {saveError && <p className="text-red-400 text-xs mt-2">{saveError}</p>}
            <div className="flex justify-end gap-3 mt-5">
              <button onClick={() => setShowAdd(false)} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">Cancel</button>
              <button
                onClick={handleAdd}
                disabled={saving || !form.url.trim() || form.events.length === 0}
                className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              >
                {saving ? 'Adding…' : 'Add Webhook'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TicketWebhooksDashboard;
