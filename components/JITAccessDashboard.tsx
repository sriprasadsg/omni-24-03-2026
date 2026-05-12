import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';

interface JITRequest {
  id: string;
  requester_id: string;
  requester_name: string;
  resource: string;
  role: string;
  reason: string;
  duration_hours: number;
  status: string;
  created_at: string;
  approved_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  approver_id: string | null;
  approver_name: string | null;
  audit_trail: { timestamp: string; action: string; actor: string; note?: string }[];
}

interface Summary {
  pending: number;
  active: number;
  expired: number;
  revoked: number;
  denied: number;
  total: number;
}

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-900/30 text-yellow-300 border-yellow-700',
  approved: 'bg-green-900/30 text-green-300 border-green-700',
  active: 'bg-blue-900/30 text-blue-300 border-blue-700',
  expired: 'bg-gray-700/50 text-gray-400 border-gray-600',
  revoked: 'bg-red-900/30 text-red-300 border-red-700',
  denied: 'bg-red-900/30 text-red-400 border-red-700',
};

export default function JITAccessDashboard() {
  const [requests, setRequests] = useState<JITRequest[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [filter, setFilter] = useState<string>('all');
  const [showCreate, setShowCreate] = useState(false);
  const [selectedReq, setSelectedReq] = useState<JITRequest | null>(null);
  const [form, setForm] = useState({ resource: '', role: '', reason: '', duration_hours: 1 });
  const [saving, setSaving] = useState(false);
  const [actionNote, setActionNote] = useState('');

  useEffect(() => { loadAll(); }, [filter]);

  async function loadAll() {
    try {
      const params = filter !== 'all' ? `?status=${filter}` : '';
      const [rRes, sRes] = await Promise.all([
        authFetch(`/api/jit/requests${params}`),
        authFetch('/api/jit/summary'),
      ]);
      const [r, s] = await Promise.all([rRes.json(), sRes.json()]);
      setRequests(r.requests || []);
      setSummary(s);
    } catch (e) { console.error(e); }
  }

  async function createRequest() {
    setSaving(true);
    try {
      const r = await authFetch('/api/jit/requests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (r.ok) { loadAll(); setShowCreate(false); setForm({ resource: '', role: '', reason: '', duration_hours: 1 }); }
      else { const d = await r.json(); alert(d.detail || 'Failed to create'); }
    } finally { setSaving(false); }
  }

  async function approveRequest(id: string) {
    await authFetch(`/api/jit/requests/${id}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note: actionNote }),
    });
    setSelectedReq(null);
    setActionNote('');
    loadAll();
  }

  async function denyRequest(id: string) {
    await authFetch(`/api/jit/requests/${id}/deny`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note: actionNote }),
    });
    setSelectedReq(null);
    setActionNote('');
    loadAll();
  }

  async function revokeRequest(id: string) {
    if (!confirm('Revoke this access session?')) return;
    await authFetch(`/api/jit/requests/${id}/revoke`, { method: 'POST' });
    loadAll();
  }

  const TABS = [
    { key: 'all', label: 'All' },
    { key: 'pending', label: 'Pending' },
    { key: 'active', label: 'Active' },
    { key: 'expired', label: 'Expired' },
  ];

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">JIT Privileged Access</h1>
          <p className="text-gray-400 text-sm mt-1">Just-in-time access requests with approval workflow and auto-expiry</p>
        </div>
        <button onClick={() => setShowCreate(true)} className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm font-medium">
          + Request Access
        </button>
      </div>

      {summary && (
        <div className="grid grid-cols-3 md:grid-cols-5 gap-3 mb-6">
          {[
            { label: 'Pending', value: summary.pending, color: 'text-yellow-400' },
            { label: 'Active', value: summary.active, color: 'text-blue-400' },
            { label: 'Expired', value: summary.expired, color: 'text-gray-400' },
            { label: 'Revoked', value: summary.revoked, color: 'text-red-400' },
            { label: 'Denied', value: summary.denied, color: 'text-red-300' },
          ].map(c => (
            <div key={c.label} className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
              <div className={`text-2xl font-bold ${c.color}`}>{c.value}</div>
              <div className="text-xs text-gray-400 mt-1">{c.label}</div>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2 mb-4">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setFilter(t.key)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${filter === t.key ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {requests.length === 0 ? (
        <div className="text-center py-20 text-gray-500">
          <div className="text-5xl mb-4">🔐</div>
          <p>No access requests found</p>
        </div>
      ) : (
        <div className="space-y-3">
          {requests.map(req => (
            <div key={req.id} className="bg-gray-800 rounded-xl p-5 border border-gray-700 hover:border-gray-500 transition-colors">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-1">
                    <span className={`text-xs px-2 py-0.5 rounded border font-medium ${STATUS_COLORS[req.status] || 'bg-gray-700 text-gray-300 border-gray-600'}`}>
                      {req.status.toUpperCase()}
                    </span>
                    <span className="font-semibold">{req.requester_name}</span>
                    <span className="text-gray-400 text-sm">→</span>
                    <span className="text-blue-300 text-sm font-mono">{req.resource}</span>
                    <span className="text-gray-400 text-xs">as</span>
                    <span className="text-purple-300 text-sm font-medium">{req.role}</span>
                  </div>
                  <p className="text-gray-400 text-sm mb-2">{req.reason}</p>
                  <div className="flex gap-4 text-xs text-gray-500">
                    <span>Duration: {req.duration_hours}h</span>
                    <span>Requested: {new Date(req.created_at).toLocaleString()}</span>
                    {req.expires_at && <span>Expires: {new Date(req.expires_at).toLocaleString()}</span>}
                    {req.approver_name && <span>Approved by: {req.approver_name}</span>}
                  </div>
                </div>
                <div className="flex gap-2 ml-4">
                  <button onClick={() => setSelectedReq(req)} className="bg-gray-700 hover:bg-gray-600 px-3 py-1.5 rounded text-xs">
                    Details
                  </button>
                  {req.status === 'pending' && (
                    <>
                      <button onClick={() => { setSelectedReq(req); }} className="bg-green-700 hover:bg-green-600 px-3 py-1.5 rounded text-xs">
                        Review
                      </button>
                    </>
                  )}
                  {req.status === 'active' && (
                    <button onClick={() => revokeRequest(req.id)} className="bg-red-900/50 hover:bg-red-900/80 px-3 py-1.5 rounded text-xs text-red-300">
                      Revoke
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-xl w-full max-w-md border border-gray-600">
            <div className="p-6">
              <div className="flex justify-between items-center mb-5">
                <h3 className="font-bold text-lg">Request Privileged Access</h3>
                <button onClick={() => setShowCreate(false)} className="text-gray-400 hover:text-white">✕</button>
              </div>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Resource *</label>
                  <input value={form.resource} onChange={e => setForm(p => ({ ...p, resource: e.target.value }))}
                    placeholder="e.g. prod-db, k8s-cluster, aws-root"
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white" />
                </div>
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Role / Permission *</label>
                  <input value={form.role} onChange={e => setForm(p => ({ ...p, role: e.target.value }))}
                    placeholder="e.g. admin, read-only, db-superuser"
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white" />
                </div>
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Business Justification *</label>
                  <textarea value={form.reason} onChange={e => setForm(p => ({ ...p, reason: e.target.value }))}
                    rows={3} placeholder="Explain why you need this access..."
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white resize-none" />
                </div>
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Duration (hours, max 8)</label>
                  <input type="number" min={1} max={8} value={form.duration_hours}
                    onChange={e => setForm(p => ({ ...p, duration_hours: Math.min(8, Math.max(1, Number(e.target.value))) }))}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white" />
                </div>
                <div className="flex gap-3 pt-2">
                  <button onClick={createRequest} disabled={saving || !form.resource || !form.role || !form.reason}
                    className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-medium">
                    {saving ? 'Submitting...' : 'Submit Request'}
                  </button>
                  <button onClick={() => setShowCreate(false)} className="px-4 py-2 rounded-lg border border-gray-600 text-sm">Cancel</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {selectedReq && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-xl w-full max-w-lg border border-gray-600 max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex justify-between items-center mb-5">
                <h3 className="font-bold text-lg">Access Request Details</h3>
                <button onClick={() => setSelectedReq(null)} className="text-gray-400 hover:text-white">✕</button>
              </div>
              <div className="space-y-3 mb-5">
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div><span className="text-gray-400">Requester:</span> <span className="text-white">{selectedReq.requester_name}</span></div>
                  <div><span className="text-gray-400">Status:</span> <span className={`px-2 py-0.5 rounded text-xs border ${STATUS_COLORS[selectedReq.status]}`}>{selectedReq.status}</span></div>
                  <div><span className="text-gray-400">Resource:</span> <span className="text-blue-300 font-mono">{selectedReq.resource}</span></div>
                  <div><span className="text-gray-400">Role:</span> <span className="text-purple-300">{selectedReq.role}</span></div>
                  <div><span className="text-gray-400">Duration:</span> <span>{selectedReq.duration_hours}h</span></div>
                  {selectedReq.expires_at && <div><span className="text-gray-400">Expires:</span> <span>{new Date(selectedReq.expires_at).toLocaleString()}</span></div>}
                </div>
                <div>
                  <p className="text-gray-400 text-xs mb-1">Justification</p>
                  <p className="text-sm bg-gray-700 rounded p-3">{selectedReq.reason}</p>
                </div>
                {selectedReq.audit_trail.length > 0 && (
                  <div>
                    <p className="text-gray-400 text-xs mb-2">Audit Trail</p>
                    <div className="space-y-1">
                      {selectedReq.audit_trail.map((e, i) => (
                        <div key={i} className="flex gap-3 text-xs text-gray-300 bg-gray-700/50 rounded px-3 py-1.5">
                          <span className="text-gray-500">{new Date(e.timestamp).toLocaleString()}</span>
                          <span className="font-medium">{e.action}</span>
                          <span className="text-gray-400">by {e.actor}</span>
                          {e.note && <span className="text-gray-500 italic">{e.note}</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              {selectedReq.status === 'pending' && (
                <div className="border-t border-gray-700 pt-4">
                  <label className="text-sm text-gray-400 block mb-2">Note (optional)</label>
                  <input value={actionNote} onChange={e => setActionNote(e.target.value)}
                    placeholder="Add a note to your decision..."
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white mb-3" />
                  <div className="flex gap-3">
                    <button onClick={() => approveRequest(selectedReq.id)}
                      className="flex-1 bg-green-700 hover:bg-green-600 px-4 py-2 rounded-lg text-sm font-medium">
                      Approve
                    </button>
                    <button onClick={() => denyRequest(selectedReq.id)}
                      className="flex-1 bg-red-900/60 hover:bg-red-900/90 px-4 py-2 rounded-lg text-sm font-medium text-red-300">
                      Deny
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
