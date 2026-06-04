import React, { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../services/apiService';

interface CabVote {
  voter: string;
  vote: string;
  reason: string;
  voted_at: string;
}

interface ChangeRequest {
  id: string;
  title: string;
  change_type: string;
  status: string;
  risk_level: string;
  impact_level: string;
  risk_assessment: string;
  rollback_plan: string;
  implementation_plan: string;
  cab_votes: CabVote[];
  required_approvals: number;
  scheduled_start: string;
  scheduled_end: string;
  assignee: string;
  reporter: string;
  created_at: string;
}

const RISK_COLORS: Record<string, string> = {
  low: 'bg-green-700/40 text-green-300 border border-green-700/50',
  medium: 'bg-yellow-700/40 text-yellow-300 border border-yellow-700/50',
  high: 'bg-orange-700/40 text-orange-300 border border-orange-700/50',
  critical: 'bg-red-700/40 text-red-300 border border-red-700/50',
};

const TYPE_COLORS: Record<string, string> = {
  standard: 'bg-blue-700/40 text-blue-300 border border-blue-700/50',
  normal: 'bg-purple-700/40 text-purple-300 border border-purple-700/50',
  emergency: 'bg-red-700/40 text-red-300 border border-red-700/50',
};

const defaultForm = {
  title: '', description: '', change_type: 'normal', risk_level: 'medium',
  impact_level: 'medium', risk_assessment: '', rollback_plan: '',
  implementation_plan: '', assignee: '',
};

const ChangeManagementDashboard: React.FC = () => {
  const [changes, setChanges] = useState<ChangeRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');

  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState(defaultForm);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [selected, setSelected] = useState<ChangeRequest | null>(null);
  const [voteReason, setVoteReason] = useState('');
  const [schedStart, setSchedStart] = useState('');
  const [schedEnd, setSchedEnd] = useState('');
  const [actionLoading, setActionLoading] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const loadChanges = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch('/api/changes');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setChanges(Array.isArray(data) ? data : (data.changes ?? []));
    } catch (e: any) {
      setError(e.message || 'Failed to load changes');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadChanges(); }, [loadChanges]);

  const filtered = changes.filter(c => {
    if (statusFilter !== 'all' && c.status !== statusFilter) return false;
    if (typeFilter !== 'all' && c.change_type !== typeFilter) return false;
    return true;
  });

  const handleCreate = async () => {
    if (!createForm.title.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      const res = await authFetch('/api/changes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(createForm),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setShowCreate(false);
      setCreateForm(defaultForm);
      await loadChanges();
    } catch (e: any) {
      setCreateError(e.message || 'Failed to create change request');
    } finally {
      setCreating(false);
    }
  };

  const handleVote = async (vote: 'approve' | 'reject') => {
    if (!selected) return;
    setActionLoading(true);
    setActionMsg(null);
    try {
      const res = await authFetch(`/api/changes/${selected.id}/vote`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vote, reason: voteReason }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setActionMsg(`Vote cast: ${vote}`);
      setVoteReason('');
      await loadChanges();
    } catch (e: any) {
      setActionMsg(`Error: ${e.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleSubmitCAB = async () => {
    if (!selected) return;
    setActionLoading(true);
    setActionMsg(null);
    try {
      const res = await authFetch(`/api/changes/${selected.id}/submit-cab`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setActionMsg('Submitted for CAB review');
      await loadChanges();
    } catch (e: any) {
      setActionMsg(`Error: ${e.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleSchedule = async () => {
    if (!selected || !schedStart || !schedEnd) return;
    setActionLoading(true);
    setActionMsg(null);
    try {
      const res = await authFetch(`/api/changes/${selected.id}/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scheduled_start: schedStart, scheduled_end: schedEnd }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setActionMsg('Change scheduled');
      setSchedStart('');
      setSchedEnd('');
      await loadChanges();
    } catch (e: any) {
      setActionMsg(`Error: ${e.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const approvedVotes = (cr: ChangeRequest) =>
    (cr.cab_votes ?? []).filter(v => v.vote === 'approve').length;

  return (
    <div className="bg-gray-900 min-h-screen text-white p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Change Management</h1>
          <p className="text-gray-400 text-sm mt-1">CAB workflow and change advisory board approvals</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          + New Change Request
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-4 flex-wrap items-center">
        <select
          className="bg-gray-800 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
        >
          {['all', 'draft', 'submitted', 'cab_review', 'approved', 'rejected', 'scheduled', 'in_progress', 'completed', 'failed'].map(s => (
            <option key={s} value={s}>{s === 'all' ? 'All Statuses' : s.replace('_', ' ')}</option>
          ))}
        </select>
        <select
          className="bg-gray-800 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none"
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
        >
          {['all', 'standard', 'normal', 'emergency'].map(t => (
            <option key={t} value={t}>{t === 'all' ? 'All Types' : t.charAt(0).toUpperCase() + t.slice(1)}</option>
          ))}
        </select>
      </div>

      {loading ? (
        <div className="text-gray-400 py-8 text-center">Loading change requests…</div>
      ) : error ? (
        <div className="text-red-400 py-8 text-center">{error}</div>
      ) : filtered.length === 0 ? (
        <div className="text-gray-500 py-8 text-center">No change requests found.</div>
      ) : (
        <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700 text-gray-400 text-xs uppercase tracking-wider">
                <th className="px-4 py-3 text-left">Title</th>
                <th className="px-4 py-3 text-left">Type</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Risk</th>
                <th className="px-4 py-3 text-left">CAB Votes</th>
                <th className="px-4 py-3 text-left">Scheduled Start</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(cr => {
                const approved = approvedVotes(cr);
                const total = cr.required_approvals || 3;
                const pct = Math.min(100, Math.round((approved / total) * 100));
                return (
                  <tr
                    key={cr.id}
                    onClick={() => { setSelected(cr); setActionMsg(null); setVoteReason(''); setSchedStart(''); setSchedEnd(''); }}
                    className="border-b border-gray-700/50 hover:bg-gray-700/40 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 font-medium text-white">{cr.title}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-semibold ${TYPE_COLORS[cr.change_type] ?? 'bg-gray-600 text-white'}`}>
                        {cr.change_type}
                      </span>
                    </td>
                    <td className="px-4 py-3 capitalize text-gray-300">{cr.status?.replace('_', ' ')}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-semibold ${RISK_COLORS[cr.risk_level] ?? 'bg-gray-600 text-white'}`}>
                        {cr.risk_level}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-20 bg-gray-700 rounded-full h-1.5">
                          <div className="bg-green-500 h-1.5 rounded-full" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="text-xs text-gray-400">{approved}/{total}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-400">
                      {cr.scheduled_start ? new Date(cr.scheduled_start).toLocaleDateString() : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
          <div className="bg-gray-800 border border-gray-700 rounded-xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
            <h2 className="text-lg font-bold text-white mb-4">New Change Request</h2>
            <div className="space-y-3">
              {[
                { key: 'title', placeholder: 'Title *', type: 'text' },
                { key: 'risk_assessment', placeholder: 'Risk Assessment', type: 'text' },
                { key: 'rollback_plan', placeholder: 'Rollback Plan', type: 'text' },
                { key: 'implementation_plan', placeholder: 'Implementation Plan', type: 'text' },
                { key: 'assignee', placeholder: 'Assignee', type: 'text' },
              ].map(({ key, placeholder }) => (
                <input
                  key={key}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                  placeholder={placeholder}
                  value={(createForm as any)[key]}
                  onChange={e => setCreateForm(f => ({ ...f, [key]: e.target.value }))}
                />
              ))}
              <textarea
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 resize-none h-16"
                placeholder="Description"
                value={createForm.description}
                onChange={e => setCreateForm(f => ({ ...f, description: e.target.value }))}
              />
              {[
                { key: 'change_type', label: 'Type', options: ['standard', 'normal', 'emergency'] },
                { key: 'risk_level', label: 'Risk Level', options: ['low', 'medium', 'high', 'critical'] },
                { key: 'impact_level', label: 'Impact Level', options: ['low', 'medium', 'high', 'critical'] },
              ].map(({ key, label, options }) => (
                <div key={key}>
                  <label className="text-xs text-gray-400 mb-1 block">{label}</label>
                  <select
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                    value={(createForm as any)[key]}
                    onChange={e => setCreateForm(f => ({ ...f, [key]: e.target.value }))}
                  >
                    {options.map(o => <option key={o} value={o}>{o.charAt(0).toUpperCase() + o.slice(1)}</option>)}
                  </select>
                </div>
              ))}
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
            <div className="flex gap-2 flex-wrap mb-4">
              <span className={`px-2 py-0.5 rounded text-xs font-semibold ${TYPE_COLORS[selected.change_type] ?? 'bg-gray-600 text-white'}`}>{selected.change_type}</span>
              <span className={`px-2 py-0.5 rounded text-xs font-semibold ${RISK_COLORS[selected.risk_level] ?? 'bg-gray-600 text-white'}`}>Risk: {selected.risk_level}</span>
              <span className={`px-2 py-0.5 rounded text-xs font-semibold ${RISK_COLORS[selected.impact_level] ?? 'bg-gray-600 text-white'}`}>Impact: {selected.impact_level}</span>
              <span className="bg-gray-700 text-gray-300 px-2 py-0.5 rounded text-xs capitalize">{selected.status?.replace('_', ' ')}</span>
            </div>
            <div className="space-y-3 text-sm">
              {[
                { label: 'Risk Assessment', value: selected.risk_assessment },
                { label: 'Rollback Plan', value: selected.rollback_plan },
                { label: 'Implementation Plan', value: selected.implementation_plan },
              ].map(({ label, value }) => value ? (
                <div key={label} className="bg-gray-900 rounded-lg p-3 border border-gray-700">
                  <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">{label}</p>
                  <p className="text-gray-200">{value}</p>
                </div>
              ) : null)}

              {/* CAB Votes */}
              <div>
                <p className="text-xs text-gray-400 uppercase tracking-wider mb-2">CAB Votes ({approvedVotes(selected)}/{selected.required_approvals || 3} approved)</p>
                {(selected.cab_votes ?? []).length === 0 ? (
                  <p className="text-gray-500 text-xs">No votes yet</p>
                ) : (
                  <div className="space-y-2">
                    {selected.cab_votes.map((v, i) => (
                      <div key={i} className="bg-gray-900 rounded-lg p-2 border border-gray-700 flex items-start gap-2">
                        <span className={`text-sm font-bold ${v.vote === 'approve' ? 'text-green-400' : 'text-red-400'}`}>
                          {v.vote === 'approve' ? '✓' : '✗'}
                        </span>
                        <div>
                          <span className="text-gray-300 text-xs font-medium">{v.voter}</span>
                          {v.reason && <p className="text-gray-400 text-xs">{v.reason}</p>}
                          <p className="text-gray-600 text-xs">{v.voted_at ? new Date(v.voted_at).toLocaleString() : ''}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="text-gray-400 text-xs space-y-1">
                <div>Reporter: {selected.reporter || '—'} | Assignee: {selected.assignee || '—'}</div>
                {selected.scheduled_start && <div>Scheduled: {new Date(selected.scheduled_start).toLocaleString()} → {new Date(selected.scheduled_end).toLocaleString()}</div>}
              </div>
            </div>

            {/* Actions */}
            <div className="mt-6 border-t border-gray-700 pt-4 space-y-4">
              {/* Submit for CAB */}
              {(selected.status === 'draft' || selected.status === 'submitted') && (
                <button
                  onClick={handleSubmitCAB}
                  disabled={actionLoading}
                  className="w-full bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                >
                  Submit for CAB Review
                </button>
              )}

              {/* Cast Vote */}
              {selected.status === 'cab_review' && (
                <div>
                  <p className="text-xs text-gray-400 mb-2 uppercase tracking-wider">Cast Vote</p>
                  <input
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 mb-2"
                    placeholder="Reason (optional)"
                    value={voteReason}
                    onChange={e => setVoteReason(e.target.value)}
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleVote('approve')}
                      disabled={actionLoading}
                      className="flex-1 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
                    >
                      Approve
                    </button>
                    <button
                      onClick={() => handleVote('reject')}
                      disabled={actionLoading}
                      className="flex-1 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
                    >
                      Reject
                    </button>
                  </div>
                </div>
              )}

              {/* Schedule */}
              {selected.status === 'approved' && (
                <div>
                  <p className="text-xs text-gray-400 mb-2 uppercase tracking-wider">Schedule Change</p>
                  <div className="space-y-2">
                    <div>
                      <label className="text-xs text-gray-500 mb-1 block">Start</label>
                      <input
                        type="datetime-local"
                        className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                        value={schedStart}
                        onChange={e => setSchedStart(e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500 mb-1 block">End</label>
                      <input
                        type="datetime-local"
                        className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                        value={schedEnd}
                        onChange={e => setSchedEnd(e.target.value)}
                      />
                    </div>
                    <button
                      onClick={handleSchedule}
                      disabled={actionLoading || !schedStart || !schedEnd}
                      className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                    >
                      Schedule
                    </button>
                  </div>
                </div>
              )}

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

export default ChangeManagementDashboard;
