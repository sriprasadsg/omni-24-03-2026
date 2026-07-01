import React, { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../services/apiService';

interface Problem {
  id: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  root_cause: string;
  workaround: string;
  permanent_fix: string;
  known_error: boolean;
  linked_incident_ids: string[];
  assignee: string;
  reporter: string;
  created_at: string;
  updated_at: string;
}

const PRIORITY_COLORS: Record<string, string> = {
  critical: 'bg-red-600 text-white',
  high: 'bg-orange-500 text-white',
  medium: 'bg-yellow-500 text-black',
  low: 'bg-green-600 text-white',
};

const STATUS_OPTIONS = ['all', 'open', 'investigating', 'known_error', 'resolved', 'closed'];

const defaultForm = { title: '', description: '', priority: 'medium', assignee: '' };

const ProblemManagementDashboard: React.FC = () => {
  const [problems, setProblems] = useState<Problem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('all');

  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState(defaultForm);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [selected, setSelected] = useState<Problem | null>(null);
  const [linkId, setLinkId] = useState('');
  const [workaroundInput, setWorkaroundInput] = useState('');
  const [actionLoading, setActionLoading] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const loadProblems = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch('/api/problems');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setProblems(Array.isArray(data) ? data : (data.problems ?? []));
    } catch (e: any) {
      setError(e.message || 'Failed to load problems');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadProblems(); }, [loadProblems]);

  const filtered = statusFilter === 'all'
    ? problems
    : problems.filter(p => p.status === statusFilter);

  const handleCreate = async () => {
    if (!createForm.title.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      const res = await authFetch('/api/problems', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(createForm),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setShowCreate(false);
      setCreateForm(defaultForm);
      await loadProblems();
    } catch (e: any) {
      setCreateError(e.message || 'Failed to create problem');
    } finally {
      setCreating(false);
    }
  };

  const handlePromoteKnownError = async () => {
    if (!selected) return;
    setActionLoading(true);
    setActionMsg(null);
    try {
      const res = await authFetch(`/api/problems/${selected.id}/promote-known-error`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workaround: workaroundInput }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setActionMsg('Promoted to known error');
      await loadProblems();
    } catch (e: any) {
      setActionMsg(`Error: ${e.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleLinkIncident = async () => {
    if (!selected || !linkId.trim()) return;
    setActionLoading(true);
    setActionMsg(null);
    try {
      const res = await authFetch(`/api/problems/${selected.id}/link-incident`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ incident_id: linkId.trim() }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setActionMsg('Incident linked');
      setLinkId('');
      await loadProblems();
    } catch (e: any) {
      setActionMsg(`Error: ${e.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="bg-gray-900 min-h-screen text-white p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Problem Management</h1>
          <p className="text-gray-400 text-sm mt-1">ITIL-aligned problem tracking and root cause analysis</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          + New Problem
        </button>
      </div>

      {/* Filter bar */}
      <div className="flex gap-2 mb-4 flex-wrap">
        {STATUS_OPTIONS.map(s => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1 rounded-full text-xs font-medium capitalize transition-colors ${
              statusFilter === s
                ? 'bg-blue-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white border border-gray-700'
            }`}
          >
            {s === 'all' ? 'All' : s.replace('_', ' ')}
          </button>
        ))}
      </div>

      {/* Table */}
      {loading ? (
        <div className="text-gray-400 py-8 text-center">Loading problems…</div>
      ) : error ? (
        <div className="text-red-400 py-8 text-center">{error}</div>
      ) : filtered.length === 0 ? (
        <div className="text-gray-500 py-8 text-center">No problems found.</div>
      ) : (
        <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700 text-gray-400 text-xs uppercase tracking-wider">
                <th className="px-4 py-3 text-left">Title</th>
                <th className="px-4 py-3 text-left">Priority</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Known Error</th>
                <th className="px-4 py-3 text-left">Assignee</th>
                <th className="px-4 py-3 text-left">Created</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(p => (
                <tr
                  key={p.id}
                  onClick={() => { setSelected(p); setActionMsg(null); setLinkId(''); setWorkaroundInput(''); }}
                  className="border-b border-gray-700/50 hover:bg-gray-700/40 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 font-medium text-white">{p.title}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${PRIORITY_COLORS[p.priority] ?? 'bg-gray-600 text-white'}`}>
                      {p.priority}
                    </span>
                  </td>
                  <td className="px-4 py-3 capitalize text-gray-300">{p.status?.replace('_', ' ')}</td>
                  <td className="px-4 py-3">
                    {p.known_error ? (
                      <span className="bg-yellow-600/30 text-yellow-400 border border-yellow-700/40 px-2 py-0.5 rounded text-xs font-semibold">Known Error</span>
                    ) : (
                      <span className="text-gray-500 text-xs">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-300">{p.assignee || '—'}</td>
                  <td className="px-4 py-3 text-gray-400">{p.created_at ? new Date(p.created_at).toLocaleDateString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
          <div className="bg-gray-800 border border-gray-700 rounded-xl w-full max-w-lg p-6">
            <h2 className="text-lg font-bold text-white mb-4">New Problem</h2>
            <div className="space-y-3">
              <input
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                placeholder="Title *"
                value={createForm.title}
                onChange={e => setCreateForm(f => ({ ...f, title: e.target.value }))}
              />
              <textarea
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 resize-none h-20"
                placeholder="Description"
                value={createForm.description}
                onChange={e => setCreateForm(f => ({ ...f, description: e.target.value }))}
              />
              <select
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                value={createForm.priority}
                onChange={e => setCreateForm(f => ({ ...f, priority: e.target.value }))}
              >
                {['critical', 'high', 'medium', 'low'].map(p => (
                  <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
                ))}
              </select>
              <input
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                placeholder="Assignee"
                value={createForm.assignee}
                onChange={e => setCreateForm(f => ({ ...f, assignee: e.target.value }))}
              />
            </div>
            {createError && <p className="text-red-400 text-xs mt-2">{createError}</p>}
            <div className="flex justify-end gap-3 mt-5">
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">Cancel</button>
              <button
                onClick={handleCreate}
                disabled={creating || !createForm.title.trim()}
                className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              >
                {creating ? 'Creating…' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Detail Panel */}
      {selected && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-start justify-end p-4">
          <div className="bg-gray-800 border border-gray-700 rounded-xl w-full max-w-xl h-full overflow-y-auto p-6">
            <div className="flex items-start justify-between mb-4">
              <h2 className="text-lg font-bold text-white flex-1 pr-4">{selected.title}</h2>
              <button onClick={() => setSelected(null)} className="text-gray-400 hover:text-white text-xl leading-none">×</button>
            </div>
            <div className="space-y-3 text-sm">
              <div className="flex gap-2 flex-wrap">
                <span className={`px-2 py-0.5 rounded text-xs font-semibold ${PRIORITY_COLORS[selected.priority] ?? 'bg-gray-600 text-white'}`}>{selected.priority}</span>
                <span className="bg-gray-700 text-gray-300 px-2 py-0.5 rounded text-xs capitalize">{selected.status?.replace('_', ' ')}</span>
                {selected.known_error && (
                  <span className="bg-yellow-600/30 text-yellow-400 border border-yellow-700/40 px-2 py-0.5 rounded text-xs font-semibold">Known Error</span>
                )}
              </div>
              <p className="text-gray-300">{selected.description || <span className="text-gray-500">No description</span>}</p>
              {selected.root_cause && (
                <div className="bg-gray-900 rounded-lg p-3 border border-gray-700">
                  <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">Root Cause</p>
                  <p className="text-gray-200 text-sm">{selected.root_cause}</p>
                </div>
              )}
              {selected.workaround && (
                <div className="bg-gray-900 rounded-lg p-3 border border-gray-700">
                  <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">Workaround</p>
                  <p className="text-gray-200 text-sm">{selected.workaround}</p>
                </div>
              )}
              {selected.permanent_fix && (
                <div className="bg-gray-900 rounded-lg p-3 border border-gray-700">
                  <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">Permanent Fix</p>
                  <p className="text-gray-200 text-sm">{selected.permanent_fix}</p>
                </div>
              )}
              {selected.linked_incident_ids?.length > 0 && (
                <div>
                  <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">Linked Incidents</p>
                  <div className="flex flex-wrap gap-1">
                    {selected.linked_incident_ids.map(id => (
                      <span key={id} className="bg-blue-900/40 text-blue-300 border border-blue-700/40 px-2 py-0.5 rounded text-xs">{id}</span>
                    ))}
                  </div>
                </div>
              )}
              <div className="text-gray-400 text-xs space-y-1">
                <div>Reporter: {selected.reporter || '—'} &nbsp;|&nbsp; Assignee: {selected.assignee || '—'}</div>
                <div>Created: {selected.created_at ? new Date(selected.created_at).toLocaleString() : '—'}</div>
              </div>
            </div>

            {/* Actions */}
            <div className="mt-6 space-y-4 border-t border-gray-700 pt-4">
              {/* Promote to Known Error */}
              {!selected.known_error && (
                <div>
                  <p className="text-xs text-gray-400 mb-2 uppercase tracking-wider">Promote to Known Error</p>
                  <textarea
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-yellow-500 resize-none h-16"
                    placeholder="Workaround description"
                    value={workaroundInput}
                    onChange={e => setWorkaroundInput(e.target.value)}
                  />
                  <button
                    onClick={handlePromoteKnownError}
                    disabled={actionLoading || !workaroundInput.trim()}
                    className="mt-2 bg-yellow-600 hover:bg-yellow-700 disabled:opacity-50 text-white px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
                  >
                    {actionLoading ? 'Processing…' : 'Promote to Known Error'}
                  </button>
                </div>
              )}

              {/* Link Incident */}
              <div>
                <p className="text-xs text-gray-400 mb-2 uppercase tracking-wider">Link Incident</p>
                <div className="flex gap-2">
                  <input
                    className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                    placeholder="Incident / Ticket ID"
                    value={linkId}
                    onChange={e => setLinkId(e.target.value)}
                  />
                  <button
                    onClick={handleLinkIncident}
                    disabled={actionLoading || !linkId.trim()}
                    className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
                  >
                    Link
                  </button>
                </div>
              </div>

              {actionMsg && (
                <p className={`text-xs ${actionMsg.startsWith('Error') ? 'text-red-400' : 'text-green-400'}`}>{actionMsg}</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProblemManagementDashboard;
