import React, { useState, useEffect, useCallback } from 'react';
import { Cloud, Play, Shield, AlertTriangle, CheckCircle, XCircle, Search, Filter, RefreshCw } from 'lucide-react';

interface CloudCheck {
  id: string;
  name: string;
  description: string;
  provider: string;
  service: string;
  severity: string;
  frameworks: string[];
  remediation: string;
}

interface CheckResult extends CloudCheck {
  checkId: string;
  checkName: string;
  result: 'PASS' | 'FAIL' | 'WARN' | 'SKIP';
  detail: string;
  accountId: string;
  checked_at: string;
}

interface Summary {
  total: number;
  pass: number;
  fail: number;
  passPct: number;
  bySeverity: Record<string, number>;
  byProvider: Record<string, { pass: number; fail: number }>;
  byService: Record<string, number>;
  coverage: number;
}

interface CloudAccount { id: string; name: string; provider: string; accountId?: string; }

const SEV_COLORS: Record<string, string> = {
  critical: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  high: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  medium: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  low: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  informational: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
};

const PROVIDER_ICONS: Record<string, string> = { aws: '☁️', azure: '🔵', gcp: '🟢' };

const authHeader = () => ({ Authorization: `Bearer ${sessionStorage.getItem('token')}`, 'Content-Type': 'application/json' });

export default function CloudChecksScanner() {
  const [checks, setChecks] = useState<CloudCheck[]>([]);
  const [results, setResults] = useState<CheckResult[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [accounts, setAccounts] = useState<CloudAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [activeTab, setActiveTab] = useState<'results' | 'library'>('results');
  const [filterProvider, setFilterProvider] = useState('');
  const [filterSeverity, setFilterSeverity] = useState('');
  const [filterResult, setFilterResult] = useState('');
  const [filterService, setFilterService] = useState('');
  const [search, setSearch] = useState('');
  const [selectedAccount, setSelectedAccount] = useState('');

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterProvider) params.set('provider', filterProvider);
      const [checksRes, resultsRes, sumRes, acctRes] = await Promise.all([
        fetch(`/api/cloud-checks?${params}`, { headers: authHeader() }),
        fetch(`/api/cloud-checks/results?${params}${selectedAccount ? `&account_id=${selectedAccount}` : ''}`, { headers: authHeader() }),
        fetch(`/api/cloud-checks/summary${selectedAccount ? `?account_id=${selectedAccount}` : ''}`, { headers: authHeader() }),
        fetch('/api/cloud-accounts', { headers: authHeader() }),
      ]);
      if (checksRes.ok) setChecks(await checksRes.json());
      if (resultsRes.ok) setResults(await resultsRes.json());
      if (sumRes.ok) setSummary(await sumRes.json());
      if (acctRes.ok) { const data = await acctRes.json(); setAccounts(Array.isArray(data) ? data : data.accounts || []); }
    } finally { setLoading(false); }
  }, [filterProvider, selectedAccount]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const runChecks = async (accountId: string, provider: string) => {
    setRunning(true);
    try {
      await fetch('/api/cloud-checks/run', { method: 'POST', headers: authHeader(), body: JSON.stringify({ accountId, provider }) });
      await fetchAll();
    } finally { setRunning(false); }
  };

  const filteredResults = results.filter(r => {
    if (filterSeverity && r.severity !== filterSeverity) return false;
    if (filterResult && r.result !== filterResult) return false;
    if (filterService && r.service !== filterService) return false;
    if (search && !r.checkName?.toLowerCase().includes(search.toLowerCase()) && !r.service?.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const filteredChecks = checks.filter(c => {
    if (filterSeverity && c.severity !== filterSeverity) return false;
    if (filterService && c.service !== filterService) return false;
    if (search && !c.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const services = [...new Set(checks.map(c => c.service))].sort();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <Shield className="w-5 h-5 text-primary-500" /> Cloud Security Checks
          <span className="text-sm font-normal text-gray-400">({checks.length} checks)</span>
        </h2>
        <div className="flex gap-2">
          <select value={selectedAccount} onChange={e => setSelectedAccount(e.target.value)} className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg">
            <option value="">All Accounts</option>
            {accounts.map(a => <option key={a.id} value={a.id}>{a.name} ({a.provider})</option>)}
          </select>
          {selectedAccount && (
            <button onClick={() => { const acc = accounts.find(a => a.id === selectedAccount); if (acc) runChecks(acc.id, acc.provider); }} disabled={running} className="flex items-center gap-2 px-3 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50">
              <Play className={`w-4 h-4 ${running ? 'animate-pulse' : ''}`} />{running ? 'Running…' : 'Run Checks'}
            </button>
          )}
          <button onClick={fetchAll} className="p-2 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="col-span-2 md:col-span-1 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
            <p className="text-xs text-gray-500 dark:text-gray-400">Pass Rate</p>
            <p className="text-3xl font-bold text-green-600 dark:text-green-400 mt-1">{summary.passPct}%</p>
            <p className="text-xs text-gray-400 mt-1">{summary.pass} / {summary.total} checks</p>
          </div>
          {['aws', 'azure', 'gcp'].map(prov => {
            const data = summary.byProvider?.[prov];
            if (!data) return null;
            const total = (data.pass || 0) + (data.fail || 0);
            const pct = total ? Math.round((data.pass || 0) / total * 100) : 0;
            return (
              <div key={prov} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
                <p className="text-xs text-gray-500 dark:text-gray-400">{PROVIDER_ICONS[prov]} {prov.toUpperCase()}</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">{pct}%</p>
                <p className="text-xs text-gray-400">{data.pass || 0} pass · {data.fail || 0} fail</p>
              </div>
            );
          })}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
            <p className="text-xs text-gray-500 dark:text-gray-400">Critical Fails</p>
            <p className="text-2xl font-bold text-red-600 dark:text-red-400 mt-1">{summary.bySeverity?.critical || 0}</p>
            <p className="text-xs text-gray-400">{summary.bySeverity?.high || 0} high · {summary.bySeverity?.medium || 0} medium</p>
          </div>
        </div>
      )}

      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
        {(['results', 'library'] as const).map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)} className={`px-4 py-2 text-sm font-medium capitalize border-b-2 -mb-px transition-colors ${activeTab === tab ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}`}>
            {tab === 'results' ? `Results (${results.length})` : `Check Library (${checks.length})`}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap gap-3">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search checks…" className="pl-9 pr-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg w-48" />
        </div>
        <select value={filterProvider} onChange={e => setFilterProvider(e.target.value)} className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg">
          <option value="">All Providers</option>
          {['aws', 'azure', 'gcp'].map(p => <option key={p}>{p}</option>)}
        </select>
        <select value={filterSeverity} onChange={e => setFilterSeverity(e.target.value)} className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg">
          <option value="">All Severities</option>
          {['critical', 'high', 'medium', 'low', 'informational'].map(s => <option key={s} className="capitalize">{s}</option>)}
        </select>
        <select value={filterService} onChange={e => setFilterService(e.target.value)} className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg">
          <option value="">All Services</option>
          {services.map(s => <option key={s}>{s}</option>)}
        </select>
        {activeTab === 'results' && (
          <select value={filterResult} onChange={e => setFilterResult(e.target.value)} className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg">
            <option value="">All Results</option>
            {['PASS', 'FAIL', 'WARN', 'SKIP'].map(r => <option key={r}>{r}</option>)}
          </select>
        )}
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" /></div>
      ) : activeTab === 'results' ? (
        filteredResults.length === 0 ? (
          <div className="text-center py-16 text-gray-400 dark:text-gray-500">
            {results.length === 0 ? 'Select a cloud account and click "Run Checks" to evaluate your cloud security posture.' : 'No results match your filters.'}
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
              <thead className="bg-gray-50 dark:bg-gray-900/50">
                <tr>
                  {['Result', 'Check', 'Provider / Service', 'Severity', 'Checked'].map(h => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {filteredResults.map(r => (
                  <tr key={r.checkId + r.accountId} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                    <td className="px-4 py-3">
                      {r.result === 'PASS'
                        ? <CheckCircle className="w-5 h-5 text-green-500" />
                        : r.result === 'FAIL'
                        ? <XCircle className="w-5 h-5 text-red-500" />
                        : <AlertTriangle className="w-5 h-5 text-yellow-500" />}
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-900 dark:text-white">{r.checkName}</p>
                      {r.result === 'FAIL' && r.detail && <p className="text-xs text-gray-400 mt-0.5 truncate max-w-xs">{r.detail}</p>}
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                      <span>{PROVIDER_ICONS[r.provider]} {r.provider?.toUpperCase()}</span>
                      <span className="text-gray-400 mx-1">·</span>
                      <span>{r.service}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${SEV_COLORS[r.severity]}`}>{r.severity}</span>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-400">{r.checked_at ? new Date(r.checked_at).toLocaleDateString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900/50">
              <tr>
                {['Check', 'Provider / Service', 'Severity', 'Frameworks'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {filteredChecks.map(c => (
                <tr key={c.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                  <td className="px-4 py-3">
                    <p className="font-medium text-gray-900 dark:text-white">{c.name}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{c.description}</p>
                  </td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                    <span>{PROVIDER_ICONS[c.provider]} {c.provider?.toUpperCase()}</span>
                    <span className="text-gray-400 mx-1">·</span>
                    <span>{c.service}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${SEV_COLORS[c.severity]}`}>{c.severity}</span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {c.frameworks.slice(0, 3).map(f => (
                        <span key={f} className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded text-xs">{f}</span>
                      ))}
                      {c.frameworks.length > 3 && <span className="text-xs text-gray-400">+{c.frameworks.length - 3}</span>}
                    </div>
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
