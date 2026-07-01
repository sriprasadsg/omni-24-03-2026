import React, { useState, useEffect, useCallback } from 'react';
import { FileText, Download, RefreshCw, CheckCircle, XCircle, AlertCircle, Edit2, Save, X } from 'lucide-react';

interface SoAEntry {
  id: string;
  controlId: string;
  controlName: string;
  description: string;
  included: boolean;
  justification: string;
  implementationStatus: string;
  implementationDescription: string;
  owner: string;
}

interface SoASummary {
  total: number;
  included: number;
  excluded: number;
  byStatus: Record<string, number>;
  completionPct: number;
}

interface Props {
  frameworkId: string;
  frameworkName?: string;
}

const STATUS_COLORS: Record<string, string> = {
  Implemented: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  Planned: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  'Not Applicable': 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
  'Compensating Control': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
};

export default function StatementOfApplicability({ frameworkId, frameworkName }: Props) {
  const [entries, setEntries] = useState<SoAEntry[]>([]);
  const [summary, setSummary] = useState<SoASummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<Partial<SoAEntry>>({});
  const [search, setSearch] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterIncluded, setFilterIncluded] = useState<'all' | 'included' | 'excluded'>('all');

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [entriesRes, summaryRes] = await Promise.all([
        fetch(`/api/soa/${frameworkId}`, { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } }),
        fetch(`/api/soa/${frameworkId}/summary`, { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } }),
      ]);
      if (entriesRes.ok) setEntries(await entriesRes.json());
      if (summaryRes.ok) setSummary(await summaryRes.json());
    } finally {
      setLoading(false);
    }
  }, [frameworkId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const generate = async () => {
    setGenerating(true);
    try {
      const res = await fetch(`/api/soa/${frameworkId}/generate`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
      });
      if (res.ok) await fetchData();
    } finally {
      setGenerating(false);
    }
  };

  const exportCsv = async () => {
    const res = await fetch(`/api/soa/${frameworkId}/export`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `soa-${frameworkId}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const startEdit = (entry: SoAEntry) => {
    setEditingId(entry.id);
    setEditForm({ included: entry.included, justification: entry.justification, implementationStatus: entry.implementationStatus, implementationDescription: entry.implementationDescription, owner: entry.owner });
  };

  const saveEdit = async (entryId: string) => {
    const res = await fetch(`/api/soa/entry/${entryId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` },
      body: JSON.stringify(editForm),
    });
    if (res.ok) {
      const updated = await res.json();
      setEntries(prev => prev.map(e => e.id === entryId ? updated : e));
      setEditingId(null);
      await fetchData();
    }
  };

  const filtered = entries.filter(e => {
    if (search && !e.controlId.toLowerCase().includes(search.toLowerCase()) && !e.controlName.toLowerCase().includes(search.toLowerCase())) return false;
    if (filterStatus && e.implementationStatus !== filterStatus) return false;
    if (filterIncluded === 'included' && !e.included) return false;
    if (filterIncluded === 'excluded' && e.included) return false;
    return true;
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <FileText className="w-5 h-5 text-primary-500" />
            Statement of Applicability
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{frameworkName || frameworkId}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={generate} disabled={generating} className="flex items-center gap-2 px-3 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50">
            <RefreshCw className={`w-4 h-4 ${generating ? 'animate-spin' : ''}`} />
            {entries.length ? 'Refresh' : 'Generate SoA'}
          </button>
          {entries.length > 0 && (
            <button onClick={exportCsv} className="flex items-center gap-2 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700">
              <Download className="w-4 h-4" /> Export CSV
            </button>
          )}
        </div>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Total Controls', value: summary.total, color: 'text-gray-900 dark:text-white' },
            { label: 'In Scope', value: summary.included, color: 'text-green-600 dark:text-green-400' },
            { label: 'Out of Scope', value: summary.excluded, color: 'text-gray-500 dark:text-gray-400' },
            { label: 'Implemented', value: `${summary.completionPct}%`, color: 'text-primary-600 dark:text-primary-400' },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
              <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
              <p className={`text-2xl font-bold mt-1 ${color}`}>{value}</p>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-3">
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search controls…" className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg w-52" />
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg">
          <option value="">All Statuses</option>
          {['Implemented', 'Planned', 'Not Applicable', 'Compensating Control'].map(s => <option key={s}>{s}</option>)}
        </select>
        <select value={filterIncluded} onChange={e => setFilterIncluded(e.target.value as any)} className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg">
          <option value="all">All</option>
          <option value="included">In Scope</option>
          <option value="excluded">Out of Scope</option>
        </select>
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" /></div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-gray-400 dark:text-gray-500">
          {entries.length === 0 ? 'Click "Generate SoA" to create entries from framework controls.' : 'No entries match your filters.'}
        </div>
      ) : (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900/50">
              <tr>
                {['Control ID', 'Control Name', 'In Scope', 'Status', 'Owner', 'Actions'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {filtered.map(entry => (
                <tr key={entry.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                  <td className="px-4 py-3 font-mono text-xs text-gray-700 dark:text-gray-300">{entry.controlId}</td>
                  <td className="px-4 py-3 text-gray-900 dark:text-white max-w-xs">
                    <div className="font-medium">{entry.controlName}</div>
                    {entry.description && <div className="text-xs text-gray-400 truncate">{entry.description}</div>}
                  </td>
                  <td className="px-4 py-3">
                    {editingId === entry.id ? (
                      <input type="checkbox" checked={!!editForm.included} onChange={e => setEditForm(f => ({ ...f, included: e.target.checked }))} className="w-4 h-4 text-primary-600 rounded" />
                    ) : (
                      entry.included
                        ? <CheckCircle className="w-5 h-5 text-green-500" />
                        : <XCircle className="w-5 h-5 text-gray-400" />
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {editingId === entry.id ? (
                      <select value={editForm.implementationStatus || ''} onChange={e => setEditForm(f => ({ ...f, implementationStatus: e.target.value }))} className="text-xs px-2 py-1 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 rounded">
                        {['Implemented', 'Planned', 'Not Applicable', 'Compensating Control'].map(s => <option key={s}>{s}</option>)}
                      </select>
                    ) : (
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[entry.implementationStatus] || ''}`}>{entry.implementationStatus}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-400">
                    {editingId === entry.id ? (
                      <input value={editForm.owner || ''} onChange={e => setEditForm(f => ({ ...f, owner: e.target.value }))} placeholder="Owner" className="text-xs px-2 py-1 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 rounded w-28" />
                    ) : entry.owner || '—'}
                  </td>
                  <td className="px-4 py-3">
                    {editingId === entry.id ? (
                      <div className="flex gap-1">
                        <button onClick={() => saveEdit(entry.id)} className="p-1 text-green-600 hover:text-green-700"><Save className="w-4 h-4" /></button>
                        <button onClick={() => setEditingId(null)} className="p-1 text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
                      </div>
                    ) : (
                      <button onClick={() => startEdit(entry)} className="p-1 text-gray-400 hover:text-primary-500"><Edit2 className="w-4 h-4" /></button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
