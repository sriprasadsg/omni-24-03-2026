import React, { useState, useEffect, useCallback } from 'react';
import { apiService } from '../services/apiService';

interface EolAsset {
  id: string;
  name: string;
  ip: string;
  os: string;
  eol_date: string;
  days_past_eol: number;
  severity: 'critical' | 'high' | 'medium' | 'low';
  last_seen: string;
}

interface RogueAsset {
  id: string;
  name: string;
  ip: string;
  mac: string;
  os: string;
  first_seen: string;
  last_seen: string;
  source: string;
  authorized: boolean;
}

interface EolSummary {
  total: number;
  by_severity: { critical: number; high: number; medium: number; low: number };
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'bg-red-900/50 text-red-300 border border-red-700',
  high: 'bg-orange-900/50 text-orange-300 border border-orange-700',
  medium: 'bg-yellow-900/50 text-yellow-300 border border-yellow-700',
  low: 'bg-blue-900/50 text-blue-300 border border-blue-700',
};

export default function AssetIntelligenceDashboard() {
  const [tab, setTab] = useState<'eol' | 'rogue'>('eol');
  const [eolAssets, setEolAssets] = useState<EolAsset[]>([]);
  const [rogueAssets, setRogueAssets] = useState<RogueAsset[]>([]);
  const [eolSummary, setEolSummary] = useState<EolSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [authorizing, setAuthorizing] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [eol, rogue, summary] = await Promise.all([
        apiService.get('/api/asset-intelligence/eol'),
        apiService.get('/api/asset-intelligence/rogue'),
        apiService.get('/api/asset-intelligence/eol/summary'),
      ]);
      setEolAssets(Array.isArray(eol) ? eol : []);
      setRogueAssets(Array.isArray(rogue) ? rogue : []);
      setEolSummary(summary);
    } catch {
      // silently fail — empty state shown
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const authorizeAsset = async (assetId: string) => {
    setAuthorizing(assetId);
    try {
      await apiService.post(`/api/asset-intelligence/rogue/${assetId}/authorize`, {});
      setRogueAssets(prev => prev.map(a => a.id === assetId ? { ...a, authorized: true } : a));
    } finally {
      setAuthorizing(null);
    }
  };

  const filteredEol = eolAssets.filter(a =>
    !search || a.name.toLowerCase().includes(search.toLowerCase()) ||
    a.os.toLowerCase().includes(search.toLowerCase()) || a.ip.includes(search)
  );

  const filteredRogue = rogueAssets.filter(a =>
    !search || a.name.toLowerCase().includes(search.toLowerCase()) ||
    a.ip.includes(search) || a.mac.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Asset Intelligence</h1>
          <p className="text-slate-400 text-sm mt-1">End-of-Life detection and unauthorized device alerting</p>
        </div>
        <button onClick={loadData} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm">
          Refresh
        </button>
      </div>

      {eolSummary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {(['critical', 'high', 'medium', 'low'] as const).map(sev => (
            <div key={sev} className="bg-slate-800 rounded-xl p-4 border border-slate-700">
              <div className="text-slate-400 text-xs uppercase tracking-wider mb-1">{sev} EOL</div>
              <div className={`text-2xl font-bold ${sev === 'critical' ? 'text-red-400' : sev === 'high' ? 'text-orange-400' : sev === 'medium' ? 'text-yellow-400' : 'text-blue-400'}`}>
                {eolSummary.by_severity[sev]}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-4 items-center">
        <div className="flex border border-slate-700 rounded-lg overflow-hidden">
          {(['eol', 'rogue'] as const).map(t => (
            <button
              key={t}
              onClick={() => { setTab(t); setSearch(''); }}
              className={`px-4 py-2 text-sm font-medium transition-colors ${tab === t ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-700'}`}
            >
              {t === 'eol' ? `EOL Assets (${eolAssets.length})` : `Rogue Assets (${rogueAssets.filter(a => !a.authorized).length})`}
            </button>
          ))}
        </div>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search..."
          className="flex-1 max-w-xs px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-white placeholder-slate-500"
        />
      </div>

      {loading ? (
        <div className="text-slate-400 text-center py-12">Loading...</div>
      ) : tab === 'eol' ? (
        <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
          {filteredEol.length === 0 ? (
            <div className="text-slate-400 text-center py-12">No end-of-life assets detected</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-slate-700">
                <tr className="text-left text-slate-400">
                  <th className="px-4 py-3">Asset</th>
                  <th className="px-4 py-3">IP</th>
                  <th className="px-4 py-3">Operating System</th>
                  <th className="px-4 py-3">EOL Date</th>
                  <th className="px-4 py-3">Days Past EOL</th>
                  <th className="px-4 py-3">Severity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {filteredEol.map(asset => (
                  <tr key={asset.id} className="hover:bg-slate-700/30 transition-colors">
                    <td className="px-4 py-3 text-white font-medium">{asset.name}</td>
                    <td className="px-4 py-3 text-slate-300 font-mono">{asset.ip}</td>
                    <td className="px-4 py-3 text-slate-300">{asset.os}</td>
                    <td className="px-4 py-3 text-slate-300">{asset.eol_date}</td>
                    <td className="px-4 py-3 text-slate-300">{asset.days_past_eol}d</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${SEVERITY_COLORS[asset.severity]}`}>
                        {asset.severity}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
          {filteredRogue.length === 0 ? (
            <div className="text-slate-400 text-center py-12">No unauthorized devices detected</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-slate-700">
                <tr className="text-left text-slate-400">
                  <th className="px-4 py-3">Device</th>
                  <th className="px-4 py-3">IP</th>
                  <th className="px-4 py-3">MAC Address</th>
                  <th className="px-4 py-3">OS</th>
                  <th className="px-4 py-3">First Seen</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {filteredRogue.map(asset => (
                  <tr key={asset.id} className="hover:bg-slate-700/30 transition-colors">
                    <td className="px-4 py-3 text-white font-medium">{asset.name || 'Unknown'}</td>
                    <td className="px-4 py-3 text-slate-300 font-mono">{asset.ip}</td>
                    <td className="px-4 py-3 text-slate-300 font-mono">{asset.mac || '—'}</td>
                    <td className="px-4 py-3 text-slate-300">{asset.os || '—'}</td>
                    <td className="px-4 py-3 text-slate-400 text-xs">{asset.first_seen ? asset.first_seen.slice(0, 10) : '—'}</td>
                    <td className="px-4 py-3">
                      {asset.authorized ? (
                        <span className="px-2 py-0.5 rounded text-xs font-medium bg-green-900/50 text-green-300 border border-green-700">Authorized</span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-xs font-medium bg-red-900/50 text-red-300 border border-red-700">Unauthorized</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {!asset.authorized && (
                        <button
                          onClick={() => authorizeAsset(asset.id)}
                          disabled={authorizing === asset.id}
                          className="px-3 py-1 bg-green-700 hover:bg-green-600 text-white rounded text-xs disabled:opacity-50"
                        >
                          {authorizing === asset.id ? 'Authorizing...' : 'Authorize'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
