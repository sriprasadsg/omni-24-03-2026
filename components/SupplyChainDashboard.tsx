import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';

interface Artifact {
  id: string;
  name: string;
  version: string;
  ecosystem: string;
  slsa_level: number;
  slsa_name: string;
  signed: boolean;
  provenance_available: boolean;
  dependency_count: number;
  vuln_count: number;
  last_scanned: string;
}

interface DepVuln {
  id: string;
  artifact_name: string;
  package: string;
  package_version: string;
  cve_id: string;
  severity: string;
  cvss_score: number;
  fix_available: boolean;
  fix_version: string;
  status: string;
}

interface Summary {
  artifacts: number;
  critical_vulns: number;
  high_vulns: number;
  slsa_4_compliant: number;
}

const SLSA_COLORS = ['text-red-400', 'text-orange-400', 'text-yellow-400', 'text-blue-400', 'text-green-400'];
const SLSA_BG = ['bg-red-900/20 border-red-700', 'bg-orange-900/20 border-orange-700', 'bg-yellow-900/20 border-yellow-700', 'bg-blue-900/20 border-blue-700', 'bg-green-900/20 border-green-700'];

const SEV_COLORS: Record<string, string> = {
  critical: 'bg-red-900/40 text-red-300 border-red-700',
  high: 'bg-orange-900/40 text-orange-300 border-orange-700',
  medium: 'bg-yellow-900/40 text-yellow-300 border-yellow-700',
  low: 'bg-gray-700 text-gray-300 border-gray-600',
};

export default function SupplyChainDashboard() {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [vulns, setVulns] = useState<DepVuln[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [tab, setTab] = useState<'artifacts' | 'vulnerabilities'>('artifacts');
  const [sevFilter, setSevFilter] = useState('');
  const [seeding, setSeeding] = useState(false);

  useEffect(() => { loadAll(); }, [sevFilter]);

  async function loadAll() {
    try {
      const [aRes, vRes, sRes] = await Promise.all([
        authFetch('/api/supply-chain-security/artifacts'),
        authFetch(`/api/supply-chain-security/vulnerabilities${sevFilter ? `?severity=${sevFilter}` : ''}`),
        authFetch('/api/supply-chain-security/summary'),
      ]);
      const [a, v, s] = await Promise.all([aRes.json(), vRes.json(), sRes.json()]);
      setArtifacts(a.artifacts || []);
      setVulns(v.vulnerabilities || []);
      setSummary(s);
    } catch (err) { console.error(err); }
  }

  async function seedData() {
    setSeeding(true);
    try {
      await authFetch('/api/supply-chain-security/seed', { method: 'POST' });
      loadAll();
    } finally { setSeeding(false); }
  }

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Supply Chain Security</h1>
          <p className="text-gray-400 text-sm mt-1">SLSA compliance, dependency vulnerability scanning, and artifact provenance</p>
        </div>
        <button onClick={seedData} disabled={seeding}
          className="bg-gray-700 hover:bg-gray-600 disabled:opacity-50 px-4 py-2 rounded-lg text-sm">
          {seeding ? 'Loading…' : 'Load Demo Data'}
        </button>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {[
            { label: 'Artifacts', value: summary.artifacts, color: 'text-blue-400' },
            { label: 'Critical Vulns', value: summary.critical_vulns, color: summary.critical_vulns > 0 ? 'text-red-400' : 'text-green-400' },
            { label: 'High Vulns', value: summary.high_vulns, color: summary.high_vulns > 0 ? 'text-orange-400' : 'text-green-400' },
            { label: 'SLSA 4 Compliant', value: summary.slsa_4_compliant, color: summary.slsa_4_compliant > 0 ? 'text-green-400' : 'text-red-400' },
          ].map(c => (
            <div key={c.label} className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
              <div className={`text-3xl font-bold ${c.color}`}>{c.value}</div>
              <div className="text-xs text-gray-400 mt-1">{c.label}</div>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2 mb-4">
        {(['artifacts', 'vulnerabilities'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium capitalize ${tab === t ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}>
            {t} ({t === 'artifacts' ? artifacts.length : vulns.length})
          </button>
        ))}
        {tab === 'vulnerabilities' && (
          <div className="ml-auto flex gap-1">
            {['', 'critical', 'high', 'medium', 'low'].map(s => (
              <button key={s} onClick={() => setSevFilter(s)}
                className={`px-2 py-0.5 rounded text-xs capitalize ${sevFilter === s ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}>
                {s || 'All'}
              </button>
            ))}
          </div>
        )}
      </div>

      {tab === 'artifacts' && (
        artifacts.length === 0 ? (
          <div className="text-center py-12 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
            <div className="text-4xl mb-3">📦</div><p>No artifacts — load demo data</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {artifacts.map(a => (
              <div key={a.id} className="bg-gray-800 rounded-xl p-5 border border-gray-700">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="font-semibold">{a.name}</h3>
                    <p className="text-xs text-gray-400">v{a.version} · {a.ecosystem}</p>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded border font-bold ${SLSA_BG[a.slsa_level]}`}>
                    <span className={SLSA_COLORS[a.slsa_level]}>{a.slsa_name}</span>
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs mb-3">
                  <div className="bg-gray-700/50 rounded px-2 py-1.5">
                    <span className="text-gray-400">Dependencies</span>
                    <p className="font-medium">{a.dependency_count}</p>
                  </div>
                  <div className={`rounded px-2 py-1.5 ${a.vuln_count > 0 ? 'bg-red-900/20' : 'bg-gray-700/50'}`}>
                    <span className="text-gray-400">Vulnerabilities</span>
                    <p className={`font-medium ${a.vuln_count > 0 ? 'text-red-400' : 'text-green-400'}`}>{a.vuln_count}</p>
                  </div>
                </div>
                <div className="flex gap-3 text-xs">
                  <span className={`px-2 py-0.5 rounded ${a.signed ? 'bg-green-900/30 text-green-300' : 'bg-red-900/30 text-red-300'}`}>
                    {a.signed ? '✓ Signed' : '✗ Unsigned'}
                  </span>
                  <span className={`px-2 py-0.5 rounded ${a.provenance_available ? 'bg-green-900/30 text-green-300' : 'bg-gray-700 text-gray-400'}`}>
                    {a.provenance_available ? '✓ Provenance' : '✗ No provenance'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {tab === 'vulnerabilities' && (
        vulns.length === 0 ? (
          <div className="text-center py-12 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
            <div className="text-4xl mb-3">✅</div><p>No vulnerabilities found</p>
          </div>
        ) : (
          <div className="space-y-2">
            {vulns.map(v => (
              <div key={v.id} className={`bg-gray-800 rounded-xl p-4 border ${v.severity === 'critical' ? 'border-red-800' : 'border-gray-700'}`}>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-xs px-2 py-0.5 rounded border font-medium capitalize ${SEV_COLORS[v.severity] || ''}`}>
                        {v.severity}
                      </span>
                      <span className="text-xs font-mono text-blue-300">{v.cve_id}</span>
                      <span className="text-xs text-gray-400">CVSS {v.cvss_score}</span>
                    </div>
                    <div className="flex gap-4 text-sm">
                      <span className="text-white font-mono">{v.package}@{v.package_version}</span>
                      <span className="text-gray-400">in <span className="text-purple-300">{v.artifact_name}</span></span>
                    </div>
                    {v.fix_available && (
                      <p className="text-xs text-green-400 mt-1">✓ Fix available: v{v.fix_version}</p>
                    )}
                  </div>
                  <span className={`text-xs capitalize ml-4 ${v.status === 'open' ? 'text-yellow-400' : v.status === 'in_progress' ? 'text-blue-400' : 'text-green-400'}`}>
                    {v.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
}
