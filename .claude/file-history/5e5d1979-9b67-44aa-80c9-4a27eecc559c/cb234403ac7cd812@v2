import React, { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

export const CloudAccountsDashboard: React.FC = () => {
  const [accounts, setAccounts] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<any>({});
  const [scanning, setScanning] = useState<Record<string, boolean>>({});
  const [results, setResults] = useState<Record<string, any[]>>({});

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [ar, sr] = await Promise.all([
        (await authFetch('/api/cloud-accounts')).json(),
        (await authFetch('/api/cloud-accounts/summary')).json(),
      ]);
      setAccounts(ar.items || []);
      setSummary(sr);
    } catch { showToast('Failed to load', 'error'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const register = async () => {
    try {
      await (await authFetch('/api/cloud-accounts', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(form) })).json();
      showToast('Account registered', 'success'); setShowForm(false); setForm({}); fetchData();
    } catch { showToast('Failed', 'error'); }
  };

  const scan = async (id: string) => {
    setScanning(s => ({...s, [id]: true}));
    try {
      const r = await (await authFetch(`/api/cloud-accounts/${id}/scan`, { method: 'POST' })).json();
      showToast(`Scan complete: ${r.ran || 0} checks`, 'success');
      fetchData();
    } catch { showToast('Scan failed', 'error'); }
    finally { setScanning(s => ({...s, [id]: false})); }
  };

  const loadResults = async (id: string) => {
    if (results[id]) return;
    try { const r = await (await authFetch(`/api/cloud-accounts/${id}/results`)).json(); setResults(s => ({...s, [id]: r.items || []})); }
    catch { showToast('Failed to load results', 'error'); }
  };

  const environments = ['prod', 'staging', 'dev'];
  const grouped = environments.reduce((acc, env) => {
    acc[env] = accounts.filter(a => (a.environment || 'dev') === env);
    return acc;
  }, {} as Record<string, any[]>);

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      {summary && (
        <div className="flex gap-4 p-3 bg-white dark:bg-gray-800 rounded shadow-sm text-xs">
          <span className="font-medium">Accounts: {summary.total_accounts}</span>
          <span className="text-green-600">Pass: {summary.pass}</span>
          <span className="text-red-600">Fail: {summary.fail}</span>
          <span>Total checks: {summary.total_checks}</span>
          {Object.entries(summary.by_provider || {}).map(([p, c]) => (
            <span key={p} className="text-gray-500">{p}: {c as number}</span>
          ))}
        </div>
      )}

      {/* Register button */}
      <div className="flex justify-end">
        <button onClick={() => setShowForm(!showForm)} className="px-3 py-1 text-xs bg-blue-600 text-white rounded">{showForm ? 'Cancel' : '+ Add Account'}</button>
      </div>

      {showForm && (
        <div className="grid grid-cols-2 gap-2 p-3 bg-gray-50 dark:bg-gray-800 rounded text-xs">
          <input placeholder="Account name" className="p-1 border rounded dark:bg-gray-700" onChange={e => setForm({...form, account_name: e.target.value})} />
          <input placeholder="Account ID" className="p-1 border rounded dark:bg-gray-700" onChange={e => setForm({...form, account_id: e.target.value})} />
          <select className="p-1 border rounded dark:bg-gray-700" onChange={e => setForm({...form, provider: e.target.value})}>
            <option value="">Provider</option><option value="aws">AWS</option><option value="azure">Azure</option><option value="gcp">GCP</option>
          </select>
          <select className="p-1 border rounded dark:bg-gray-700" onChange={e => setForm({...form, environment: e.target.value})}>
            <option value="">Environment</option><option value="prod">Prod</option><option value="staging">Staging</option><option value="dev">Dev</option>
          </select>
          <button onClick={register} className="px-2 py-1 bg-blue-600 text-white rounded col-span-2">Register</button>
        </div>
      )}

      {loading && <p className="text-xs text-gray-400">Loading...</p>}

      {/* Accounts by environment */}
      {['prod', 'staging', 'dev'].map(env => {
        const envAccounts = grouped[env] || [];
        if (envAccounts.length === 0) return null;
        return (
          <div key={env} className="space-y-2">
            <h4 className="text-xs font-semibold uppercase text-gray-500 border-b dark:border-gray-700 pb-1">{env} ({envAccounts.length})</h4>
            {envAccounts.map((a: any) => (
              <div key={a.id} className="p-3 bg-white dark:bg-gray-800 rounded shadow-sm text-xs space-y-1">
                <div className="flex items-center justify-between">
                  <div><span className="font-medium">{a.account_name}</span> <span className="text-gray-400">{a.provider} · {a.account_id}</span></div>
                  <span className={`px-1.5 py-0.5 rounded ${a.scan_status === 'idle' ? 'bg-gray-100 text-gray-600' : a.scan_status === 'scanning' ? 'bg-blue-100 text-blue-600' : 'bg-red-100 text-red-600'}`}>{a.scan_status}</span>
                </div>
                {a.last_scan && <div className="text-gray-400">Last scan: {new Date(a.last_scan).toLocaleString()}</div>}
                <div className="flex gap-1 pt-1">
                  <button onClick={() => scan(a.id)} disabled={scanning[a.id]} className="px-2 py-0.5 bg-blue-600 text-white rounded disabled:opacity-50 text-[10px]">
                    {scanning[a.id] ? 'Scanning...' : 'Scan Now'}
                  </button>
                  <button onClick={() => loadResults(a.id)} className="px-2 py-0.5 bg-gray-200 dark:bg-gray-600 rounded text-[10px]">Results</button>
                </div>
                {(results[a.id] || []).length > 0 && (
                  <div className="mt-1 max-h-20 overflow-y-auto space-y-0.5">
                    {(results[a.id] || []).slice(0, 5).map((r: any, i: number) => (
                      <div key={i} className="flex gap-1 text-[10px]">
                        <span className={`w-1.5 h-1.5 rounded-full mt-0.5 shrink-0 ${r.result === 'PASS' ? 'bg-green-500' : 'bg-red-500'}`} />
                        <span className="text-gray-500 truncate">{r.checkName || r.checkId}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        );
      })}

      {!loading && accounts.length === 0 && <p className="text-xs text-gray-400 italic">No cloud accounts registered.</p>}
    </div>
  );
};
