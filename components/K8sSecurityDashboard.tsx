import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';

interface Cluster {
  id: string;
  name: string;
  provider: string;
  k8s_version: string;
  node_count: number;
  namespace_count: number;
  pod_count: number;
  status: string;
  last_scanned: string | null;
  risk_score: number;
}

interface Finding {
  id: string;
  cluster_id: string;
  control_id: string;
  category: string;
  title: string;
  severity: string;
  status: string;
  remediation: string;
  detected_at: string;
}

interface Summary {
  clusters: number;
  critical_findings: number;
  high_findings: number;
  total_findings: number;
}

const SEV_COLORS: Record<string, string> = {
  critical: 'bg-red-900/40 text-red-300 border-red-700',
  high: 'bg-orange-900/40 text-orange-300 border-orange-700',
  medium: 'bg-yellow-900/40 text-yellow-300 border-yellow-700',
  low: 'bg-gray-700 text-gray-300 border-gray-600',
};

const PROVIDERS = ['self-managed', 'eks', 'gke', 'aks', 'k3s'];

export default function K8sSecurityDashboard() {
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [selectedCluster, setSelectedCluster] = useState<string | null>(null);
  const [scanning, setScanning] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: '', provider: 'eks', k8s_version: '1.28', node_count: 3, endpoint: '' });
  const [saving, setSaving] = useState(false);
  const [severityFilter, setSeverityFilter] = useState('');

  useEffect(() => { loadAll(); }, []);

  async function loadAll() {
    try {
      const [cRes, fRes, sRes] = await Promise.all([
        authFetch('/api/k8s-security/clusters'),
        authFetch(`/api/k8s-security/findings${selectedCluster ? `?cluster_id=${selectedCluster}` : ''}${severityFilter ? `${selectedCluster ? '&' : '?'}severity=${severityFilter}` : ''}`),
        authFetch('/api/k8s-security/summary'),
      ]);
      const [c, f, s] = await Promise.all([cRes.json(), fRes.json(), sRes.json()]);
      setClusters(c.clusters || []);
      setFindings(f.findings || []);
      setSummary(s);
    } catch (err) { console.error(err); }
  }

  useEffect(() => { loadAll(); }, [selectedCluster, severityFilter]);

  async function scanCluster(id: string) {
    setScanning(id);
    try {
      await authFetch(`/api/k8s-security/clusters/${id}/scan`, { method: 'POST' });
      loadAll();
    } finally { setScanning(null); }
  }

  async function addCluster() {
    setSaving(true);
    try {
      const r = await authFetch('/api/k8s-security/clusters', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (r.ok) { loadAll(); setShowAdd(false); }
    } finally { setSaving(false); }
  }

  const riskColor = (score: number) =>
    score >= 0.6 ? 'text-red-400' : score >= 0.3 ? 'text-yellow-400' : 'text-green-400';

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Kubernetes Security</h1>
          <p className="text-gray-400 text-sm mt-1">CIS Benchmark assessment, RBAC audit, pod security, and container hardening</p>
        </div>
        <button onClick={() => setShowAdd(true)} className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm font-medium">
          + Add Cluster
        </button>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {[
            { label: 'Clusters', value: summary.clusters, color: 'text-blue-400' },
            { label: 'Critical Findings', value: summary.critical_findings, color: summary.critical_findings > 0 ? 'text-red-400' : 'text-green-400' },
            { label: 'High Findings', value: summary.high_findings, color: summary.high_findings > 0 ? 'text-orange-400' : 'text-green-400' },
            { label: 'Total Findings', value: summary.total_findings, color: 'text-purple-400' },
          ].map(c => (
            <div key={c.label} className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
              <div className={`text-3xl font-bold ${c.color}`}>{c.value}</div>
              <div className="text-xs text-gray-400 mt-1">{c.label}</div>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">Clusters</h2>
          {clusters.length === 0 ? (
            <div className="text-center py-10 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
              <div className="text-4xl mb-2">☸️</div>
              <p className="text-sm">No clusters registered</p>
              <button onClick={() => setShowAdd(true)} className="mt-3 text-blue-400 text-xs hover:underline">Add a cluster</button>
            </div>
          ) : (
            clusters.map(c => (
              <div key={c.id}
                onClick={() => setSelectedCluster(c.id === selectedCluster ? null : c.id)}
                className={`bg-gray-800 rounded-xl p-4 border cursor-pointer transition-colors ${selectedCluster === c.id ? 'border-blue-500' : 'border-gray-700 hover:border-gray-500'}`}>
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <h3 className="font-medium">☸️ {c.name}</h3>
                    <p className="text-xs text-gray-400">{c.provider.toUpperCase()} · v{c.k8s_version}</p>
                  </div>
                  <span className={`text-sm font-bold ${riskColor(c.risk_score)}`}>
                    {Math.round(c.risk_score * 100)}%
                  </span>
                </div>
                <div className="flex gap-3 text-xs text-gray-400 mb-3">
                  <span>{c.node_count} nodes</span>
                  <span>{c.namespace_count} ns</span>
                  <span>{c.pod_count} pods</span>
                </div>
                <button onClick={(e) => { e.stopPropagation(); scanCluster(c.id); }}
                  disabled={scanning === c.id}
                  className="w-full bg-gray-700 hover:bg-gray-600 disabled:opacity-50 px-3 py-1.5 rounded text-xs">
                  {scanning === c.id ? 'Scanning…' : c.last_scanned ? `Re-scan · ${new Date(c.last_scanned).toLocaleDateString()}` : 'Run CIS Scan'}
                </button>
              </div>
            ))
          )}
        </div>

        <div className="lg:col-span-2 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
              CIS Benchmark Findings {selectedCluster && `— ${clusters.find(c => c.id === selectedCluster)?.name}`}
            </h2>
            <div className="flex gap-1">
              {['', 'critical', 'high', 'medium'].map(s => (
                <button key={s} onClick={() => setSeverityFilter(s)}
                  className={`px-2 py-0.5 rounded text-xs capitalize ${severityFilter === s ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}>
                  {s || 'All'}
                </button>
              ))}
            </div>
          </div>
          {findings.length === 0 ? (
            <div className="text-center py-12 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
              <p>{clusters.length === 0 ? 'Add a cluster and run a scan to see findings' : 'No findings — run a scan'}</p>
            </div>
          ) : (
            <div className="space-y-2">
              {findings.map(f => (
                <div key={f.id} className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                  <div className="flex items-start justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-500 font-mono">{f.control_id}</span>
                      <span className={`text-xs px-2 py-0.5 rounded border font-medium capitalize ${SEV_COLORS[f.severity] || ''}`}>
                        {f.severity}
                      </span>
                      <span className="text-xs text-gray-500 bg-gray-700 px-2 py-0.5 rounded">{f.category}</span>
                    </div>
                    <span className={`text-xs capitalize ${f.status === 'fail' ? 'text-red-400' : 'text-yellow-400'}`}>{f.status}</span>
                  </div>
                  <p className="text-sm font-medium">{f.title}</p>
                  <p className="text-xs text-gray-400 mt-1">{f.remediation}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {showAdd && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-xl w-full max-w-md border border-gray-600">
            <div className="p-6">
              <div className="flex justify-between items-center mb-5">
                <h3 className="font-bold text-lg">Register Kubernetes Cluster</h3>
                <button onClick={() => setShowAdd(false)} className="text-gray-400 hover:text-white">✕</button>
              </div>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Cluster Name *</label>
                  <input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                    placeholder="e.g. prod-us-east-1"
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-sm text-gray-400 block mb-1">Provider</label>
                    <select value={form.provider} onChange={e => setForm(p => ({ ...p, provider: e.target.value }))}
                      className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white">
                      {PROVIDERS.map(p => <option key={p} value={p}>{p.toUpperCase()}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-sm text-gray-400 block mb-1">K8s Version</label>
                    <input value={form.k8s_version} onChange={e => setForm(p => ({ ...p, k8s_version: e.target.value }))}
                      className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white" />
                  </div>
                </div>
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Node Count</label>
                  <input type="number" min={1} value={form.node_count}
                    onChange={e => setForm(p => ({ ...p, node_count: Number(e.target.value) }))}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white" />
                </div>
                <div className="flex gap-3 pt-2">
                  <button onClick={addCluster} disabled={saving || !form.name}
                    className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-medium">
                    {saving ? 'Registering…' : 'Register Cluster'}
                  </button>
                  <button onClick={() => setShowAdd(false)} className="px-4 py-2 rounded-lg border border-gray-600 text-sm">Cancel</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
