import React, { useState, useEffect, useCallback } from 'react';
import { UserCheck, Plus, AlertTriangle, Clock, CheckCircle, ChevronRight, Play, Award } from 'lucide-react';

interface ScopeUser { userId: string; userName: string; email?: string; role?: string; }
interface Decision { userId: string; userName: string; decision: string; reason: string; decidedAt: string; }
interface Review {
  id: string;
  name: string;
  description: string;
  type: string;
  frequency: string;
  status: string;
  reviewer: string;
  nextReviewDate: string;
  scopeUsers: ScopeUser[];
  decisions: Decision[];
  created_at: string;
  completedAt?: string;
}

interface Summary { total: number; byStatus: Record<string, number>; overdue: number; upcomingNext30Days: number; }

const STATUS_COLORS: Record<string, string> = {
  Scheduled: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  'In Progress': 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  Completed: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  Overdue: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  Cancelled: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
};

const DECISION_COLORS: Record<string, string> = {
  Approved: 'text-green-600 dark:text-green-400',
  Revoked: 'text-red-600 dark:text-red-400',
  Modified: 'text-yellow-600 dark:text-yellow-400',
  Deferred: 'text-gray-500 dark:text-gray-400',
};

const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}`, 'Content-Type': 'application/json' });

export default function AccessReviewDashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [selected, setSelected] = useState<Review | null>(null);
  const [view, setView] = useState<'list' | 'create' | 'detail'>('list');
  const [loading, setLoading] = useState(true);
  const [decisions, setDecisions] = useState<Record<string, { decision: string; reason: string }>>({});
  const [newReview, setNewReview] = useState({ name: '', description: '', type: 'User Access', frequency: 'Quarterly', reviewer: '' });
  const [submitting, setSubmitting] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [sumRes, listRes] = await Promise.all([
        fetch('/api/access-reviews/summary', { headers: authHeader() }),
        fetch('/api/access-reviews', { headers: authHeader() }),
      ]);
      if (sumRes.ok) setSummary(await sumRes.json());
      if (listRes.ok) setReviews(await listRes.json());
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const openDetail = async (r: Review) => {
    const res = await fetch(`/api/access-reviews/${r.id}`, { headers: authHeader() });
    if (res.ok) {
      const data = await res.json();
      setSelected(data);
      const init: Record<string, { decision: string; reason: string }> = {};
      (data.scopeUsers || []).forEach((u: ScopeUser) => {
        const existing = (data.decisions || []).find((d: Decision) => d.userId === u.userId);
        init[u.userId] = existing ? { decision: existing.decision, reason: existing.reason } : { decision: 'Approved', reason: '' };
      });
      setDecisions(init);
    }
    setView('detail');
  };

  const create = async () => {
    if (!newReview.name.trim()) return;
    const res = await fetch('/api/access-reviews', { method: 'POST', headers: authHeader(), body: JSON.stringify(newReview) });
    if (res.ok) { await fetchAll(); setView('list'); setNewReview({ name: '', description: '', type: 'User Access', frequency: 'Quarterly', reviewer: '' }); }
  };

  const startReview = async () => {
    if (!selected) return;
    const res = await fetch(`/api/access-reviews/${selected.id}/start`, { method: 'POST', headers: authHeader() });
    if (res.ok) { setSelected(await res.json()); await fetchAll(); }
  };

  const submitDecisions = async () => {
    if (!selected) return;
    setSubmitting(true);
    try {
      const payload = Object.entries(decisions).map(([userId, d]) => ({
        userId,
        userName: selected.scopeUsers.find(u => u.userId === userId)?.userName || userId,
        ...d,
      }));
      const res = await fetch(`/api/access-reviews/${selected.id}/decisions`, { method: 'PUT', headers: authHeader(), body: JSON.stringify({ decisions: payload }) });
      if (res.ok) setSelected(await res.json());
    } finally { setSubmitting(false); }
  };

  const complete = async () => {
    if (!selected) return;
    const res = await fetch(`/api/access-reviews/${selected.id}/complete`, { method: 'PUT', headers: authHeader() });
    if (res.ok) { setSelected(await res.json()); await fetchAll(); }
  };

  if (view === 'create') return (
    <div className="space-y-6 max-w-lg">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Schedule Access Review</h2>
        <button onClick={() => setView('list')} className="text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">Cancel</button>
      </div>
      <div className="space-y-3">
        <input value={newReview.name} onChange={e => setNewReview(p => ({ ...p, name: e.target.value }))} placeholder="Review name *" className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg text-sm" />
        <input value={newReview.description} onChange={e => setNewReview(p => ({ ...p, description: e.target.value }))} placeholder="Description" className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg text-sm" />
        <div className="grid grid-cols-2 gap-3">
          <select value={newReview.type} onChange={e => setNewReview(p => ({ ...p, type: e.target.value }))} className="px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg text-sm">
            {['User Access', 'Privileged Access', 'Vendor Access', 'Application Access', 'Service Account'].map(t => <option key={t}>{t}</option>)}
          </select>
          <select value={newReview.frequency} onChange={e => setNewReview(p => ({ ...p, frequency: e.target.value }))} className="px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg text-sm">
            {['Weekly', 'Monthly', 'Quarterly', 'Semi-Annual', 'Annual'].map(f => <option key={f}>{f}</option>)}
          </select>
        </div>
        <input value={newReview.reviewer} onChange={e => setNewReview(p => ({ ...p, reviewer: e.target.value }))} placeholder="Reviewer" className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg text-sm" />
      </div>
      <button onClick={create} disabled={!newReview.name.trim()} className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 text-sm">Schedule Review</button>
    </div>
  );

  if (view === 'detail' && selected) return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <button onClick={() => setView('list')} className="text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">← Back</button>
        <ChevronRight className="w-4 h-4 text-gray-400" />
        <span className="text-sm font-medium text-gray-900 dark:text-white">{selected.name}</span>
        <span className={`ml-1 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[selected.status]}`}>{selected.status}</span>
      </div>

      <div className="flex gap-2 flex-wrap">
        {selected.status === 'Scheduled' || selected.status === 'Overdue' ? (
          <button onClick={startReview} className="flex items-center gap-2 px-3 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700">
            <Play className="w-4 h-4" /> Start Review
          </button>
        ) : selected.status === 'In Progress' ? (
          <>
            <button onClick={submitDecisions} disabled={submitting} className="flex items-center gap-2 px-3 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50">
              {submitting ? 'Saving…' : 'Save Decisions'}
            </button>
            <button onClick={complete} className="flex items-center gap-2 px-3 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700">
              <Award className="w-4 h-4" /> Complete Review
            </button>
          </>
        ) : null}
      </div>

      <div className="grid grid-cols-3 gap-4 text-sm">
        {[{ label: 'Type', value: selected.type }, { label: 'Frequency', value: selected.frequency }, { label: 'Reviewer', value: selected.reviewer }, { label: 'Next Review', value: selected.nextReviewDate ? new Date(selected.nextReviewDate).toLocaleDateString() : '—' }, { label: 'Users in Scope', value: selected.scopeUsers?.length || 0 }, { label: 'Decisions', value: selected.decisions?.length || 0 }].map(({ label, value }) => (
          <div key={label} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
            <p className="font-medium text-gray-900 dark:text-white mt-0.5">{value}</p>
          </div>
        ))}
      </div>

      {selected.scopeUsers?.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <h3 className="font-medium text-gray-900 dark:text-white mb-4">Access Decisions</h3>
          <div className="space-y-3">
            {selected.scopeUsers.map(u => (
              <div key={u.userId} className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 dark:text-white">{u.userName}</p>
                  {u.role && <p className="text-xs text-gray-400">{u.role}</p>}
                </div>
                {selected.status === 'In Progress' ? (
                  <div className="flex items-center gap-2">
                    <select value={decisions[u.userId]?.decision || 'Approved'} onChange={e => setDecisions(d => ({ ...d, [u.userId]: { ...d[u.userId], decision: e.target.value } }))} className="text-xs px-2 py-1 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 rounded">
                      {['Approved', 'Revoked', 'Modified', 'Deferred'].map(d => <option key={d}>{d}</option>)}
                    </select>
                    <input value={decisions[u.userId]?.reason || ''} onChange={e => setDecisions(d => ({ ...d, [u.userId]: { ...d[u.userId], reason: e.target.value } }))} placeholder="Reason" className="text-xs px-2 py-1 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 rounded w-32" />
                  </div>
                ) : (
                  <span className={`text-sm font-medium ${DECISION_COLORS[decisions[u.userId]?.decision || ''] || 'text-gray-400'}`}>
                    {decisions[u.userId]?.decision || '—'}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <UserCheck className="w-5 h-5 text-primary-500" /> Access Reviews
        </h2>
        <button onClick={() => setView('create')} className="flex items-center gap-2 px-3 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700">
          <Plus className="w-4 h-4" /> Schedule Review
        </button>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Total Reviews', value: summary.total, icon: UserCheck, color: 'text-gray-900 dark:text-white' },
            { label: 'Overdue', value: summary.overdue, icon: AlertTriangle, color: 'text-red-600 dark:text-red-400' },
            { label: 'Upcoming (30d)', value: summary.upcomingNext30Days, icon: Clock, color: 'text-yellow-600 dark:text-yellow-400' },
            { label: 'Completed', value: summary.byStatus?.Completed || 0, icon: CheckCircle, color: 'text-green-600 dark:text-green-400' },
          ].map(({ label, value, icon: Icon, color }) => (
            <div key={label} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-center gap-2 text-gray-400 text-xs mb-1"><Icon className="w-3.5 h-3.5" />{label}</div>
              <p className={`text-2xl font-bold ${color}`}>{value}</p>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12"><div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" /></div>
      ) : reviews.length === 0 ? (
        <div className="text-center py-16 text-gray-400 dark:text-gray-500">No access reviews scheduled yet.</div>
      ) : (
        <div className="grid gap-3">
          {reviews.map(r => (
            <button key={r.id} onClick={() => openDetail(r)} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 flex items-center justify-between hover:shadow-md transition-shadow text-left w-full">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium text-gray-900 dark:text-white text-sm">{r.name}</span>
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[r.status]}`}>{r.status}</span>
                </div>
                <div className="flex gap-3 text-xs text-gray-400">
                  <span>{r.type}</span>
                  <span>{r.frequency}</span>
                  <span>Next: {r.nextReviewDate ? new Date(r.nextReviewDate).toLocaleDateString() : '—'}</span>
                </div>
              </div>
              <ChevronRight className="w-4 h-4 text-gray-400 ml-4 shrink-0" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
