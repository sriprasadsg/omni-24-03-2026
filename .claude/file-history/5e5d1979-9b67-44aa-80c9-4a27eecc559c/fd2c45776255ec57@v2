import React, { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

const STATUS_STYLES: Record<string, string> = { compliant: 'bg-green-100 text-green-800', at_risk: 'bg-red-100 text-red-800', in_progress: 'bg-amber-100 text-amber-800' };

export const ProgramsDashboard: React.FC = () => {
  const [programs, setPrograms] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<any>({});
  const [editing, setEditing] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    try { const r = await (await authFetch('/api/programs')).json(); setPrograms(r.items || []); }
    catch { showToast('Failed to load', 'error'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetch(); }, [fetch]);

  const submit = async () => {
    try {
      await (await authFetch('/api/programs', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(form) })).json();
      showToast('Program created', 'success'); setShowForm(false); setForm({}); fetch();
    } catch { showToast('Failed', 'error'); }
  };

  const del = async (id: string) => {
    try { await authFetch(`/api/programs/${id}`, { method: 'DELETE' }); showToast('Deleted', 'success'); fetch(); }
    catch { showToast('Delete failed', 'error'); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between"><h3 className="text-sm font-semibold">Programs ({programs.length})</h3>
        <button onClick={() => setShowForm(!showForm)} className="px-3 py-1 text-xs bg-blue-600 text-white rounded">{showForm ? 'Cancel' : '+ New Program'}</button></div>

      {showForm && (
        <div className="grid grid-cols-2 gap-2 p-3 bg-gray-50 dark:bg-gray-800 rounded text-xs">
          <input placeholder="Name" className="p-1 border rounded dark:bg-gray-700" onChange={e => setForm({...form, name: e.target.value})} />
          <input placeholder="Framework ID (soc2)" className="p-1 border rounded dark:bg-gray-700" onChange={e => setForm({...form, framework_id: e.target.value})} />
          <input placeholder="Owner" className="p-1 border rounded dark:bg-gray-700" onChange={e => setForm({...form, owner: e.target.value})} />
          <input placeholder="Description" className="p-1 border rounded dark:bg-gray-700 col-span-2" onChange={e => setForm({...form, description: e.target.value})} />
          <button onClick={submit} className="px-2 py-1 bg-blue-600 text-white rounded col-span-2">Create</button>
        </div>
      )}

      {loading && <p className="text-xs text-gray-400">Loading...</p>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {programs.map((p, i) => {
          const s = p.status_rollup || {};
          const st = s.status || 'in_progress';
          const pct = s.total > 0 ? Math.round((s.passing / s.total) * 100) : 0;
          return (
            <div key={p.id || i} className="p-3 bg-white dark:bg-gray-800 rounded shadow-sm text-xs space-y-2">
              <div className="flex items-center justify-between">
                <div><span className="font-medium">{p.name}</span> <span className="text-gray-400">{p.framework_id}</span></div>
                <span className={`px-1.5 py-0.5 rounded font-medium ${STATUS_STYLES[st] || STATUS_STYLES.in_progress}`}>{st.replace('_', ' ')}</span>
              </div>
              {p.description && <p className="text-gray-500">{p.description}</p>}
              <div className="text-gray-500">Owner: {p.owner} · Controls: {p.control_ids?.length || 0}</div>
              {s.total > 0 && (
                <div className="space-y-1">
                  <div className="w-full h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${st === 'compliant' ? 'bg-green-500' : st === 'at_risk' ? 'bg-red-500' : 'bg-amber-500'}`} style={{width: `${pct}%`}} />
                  </div>
                  <div className="flex justify-between text-gray-400 text-[10px]">
                    <span>{s.passing} pass</span><span>{s.failing} fail</span><span>{s.not_assessed} na</span><span>{pct}%</span>
                  </div>
                </div>
              )}
              <div className="flex gap-1 pt-1">
                <button onClick={() => setEditing(p.id)} className="px-2 py-0.5 bg-gray-200 dark:bg-gray-600 rounded">Controls</button>
                <button onClick={() => del(p.id)} className="px-2 py-0.5 bg-red-100 dark:bg-red-900/30 text-red-600 rounded">Delete</button>
              </div>
            </div>
          );
        })}
      </div>
      {!loading && programs.length === 0 && <p className="text-xs text-gray-400 italic">No programs yet.</p>}
    </div>
  );
};
