import React, { useState, useCallback, useEffect, useMemo } from 'react';
import { Shield, AlertTriangle, CheckCircle, XCircle, RefreshCw, Upload, Terminal, Server, FileCode } from 'lucide-react';

interface IaCResult {
  check_id: string;
  check_name: string;
  severity: string;
  status: string;
  message: string;
  line: number | null;
}

interface IaCScanResponse {
  scan_id: string;
  provider: string;
  total: number;
  fail: number;
  findings: IaCResult[];
  scanned_at: string;
  warning?: string;
}

interface ContainerVuln {
  id: string;
  pkg_name: string;
  installed_version: string;
  fixed_version: string;
  severity: string;
  title: string;
  description: string;
}

interface ContainerScanResponse {
  scan_id: string;
  image: string;
  trivy: boolean;
  simulated?: boolean;
  vulns: ContainerVuln[];
  total: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  scanned_at: string;
  note?: string;
}

type TabType = 'iac' | 'container';

// Matches CloudChecksScanner.tsx's SEV_COLORS, reused verbatim per UI-SPEC.
const SEV_COLORS: Record<string, string> = {
  critical: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  high: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  medium: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  low: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
};
const SEV_FALLBACK = 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400';
const SEV_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };

function timeAgo(ts: string) {
  const d = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (d < 60) return `${Math.max(0, d)}s ago`;
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  return `${Math.floor(d / 3600)}h ago`;
}

async function describeError(r: Response, action: string): Promise<string> {
  try {
    const body = await r.json();
    const detail = body?.detail || body?.message;
    return detail ? `${action} failed: ${r.status} — ${detail}` : `${action} failed (${r.status})`;
  } catch {
    return `${action} failed (${r.status})`;
  }
}

export function IacContainerDashboard() {
  const [tab, setTab] = useState<TabType>('iac');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // IaC state
  const [iacCode, setIacCode] = useState('');
  const [iacFilename, setIacFilename] = useState('main.tf');
  const [iacResult, setIacResult] = useState<IaCScanResponse | null>(null);
  const [iacHistory, setIacHistory] = useState<IaCScanResponse[]>([]);
  const [iacConfig, setIacConfig] = useState<{ excluded_paths: string[]; severity_threshold: string; auto_scan_enabled: boolean } | null>(null);

  // Container state
  const [imageName, setImageName] = useState('nginx:latest');
  const [containerResult, setContainerResult] = useState<ContainerScanResponse | null>(null);
  const [containerHistory, setContainerHistory] = useState<ContainerScanResponse[]>([]);

  const token = sessionStorage.getItem('token') || sessionStorage.getItem('access_token');
  const headers = token ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' };

  const fetchIacHistory = useCallback(async () => {
    try {
      const r = await fetch('/api/iac/results', { headers }).then(r => r.ok ? r.json() : null);
      if (r) setIacHistory(r.items || []);
    } catch { /* network error — leave existing history in place */ }
  }, []);

  const fetchContainerHistory = useCallback(async () => {
    try {
      const r = await fetch('/api/container/results', { headers }).then(r => r.ok ? r.json() : null);
      if (r) setContainerHistory(r.items || []);
    } catch { /* network error — leave existing history in place */ }
  }, []);

  const fetchIacConfig = useCallback(async () => {
    try {
      const r = await fetch('/api/iac/scan-config', { headers }).then(r => r.ok ? r.json() : null);
      if (r) setIacConfig(r.config);
    } catch { /* network error — leave existing config in place */ }
  }, []);

  useEffect(() => {
    fetchIacHistory();
    fetchContainerHistory();
    fetchIacConfig();
  }, []);

  const runIacScan = async () => {
    if (!iacCode.trim()) return;
    setLoading(true); setError('');
    try {
      const r = await fetch('/api/iac/scan', {
        method: 'POST', headers,
        body: JSON.stringify({ code: iacCode, filename: iacFilename }),
      });
      if (!r.ok) { setError(await describeError(r, 'Scan')); return; }
      const data: IaCScanResponse = await r.json();
      setIacResult(data);
      fetchIacHistory();
    } catch (e: any) { setError(`Scan failed: ${e.message}`); }
    finally { setLoading(false); }
  };

  const runContainerScan = async () => {
    if (!imageName.trim()) return;
    setLoading(true); setError('');
    try {
      const r = await fetch('/api/container/scan', {
        method: 'POST', headers,
        body: JSON.stringify({ image_name: imageName }),
      });
      if (!r.ok) { setError(await describeError(r, 'Scan')); return; }
      const data: ContainerScanResponse = await r.json();
      setContainerResult(data);
      fetchContainerHistory();
    } catch (e: any) { setError(`Scan failed: ${e.message}`); }
    finally { setLoading(false); }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIacFilename(file.name);
    const reader = new FileReader();
    reader.onload = (ev) => setIacCode(ev.target?.result as string || '');
    reader.readAsText(file);
  };

  const sortedFindings = useMemo(() => {
    return [...(iacResult?.findings || [])].sort((a, b) => {
      const oa = SEV_ORDER[(a.severity || '').toLowerCase()] ?? 9;
      const ob = SEV_ORDER[(b.severity || '').toLowerCase()] ?? 9;
      return oa - ob;
    });
  }, [iacResult]);

  const statusBadgeClass = (status: string) => {
    const isFail = status.toUpperCase() === 'FAIL';
    return `inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${isFail ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'}`;
  };

  const Spinner = () => (
    <div className="flex justify-center py-12"><div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <Shield className="w-5 h-5 text-blue-600 dark:text-blue-400" /> IaC & Container Security
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Infrastructure-as-Code scanning · Container vulnerability analysis</p>
        </div>
        <button onClick={() => { fetchIacHistory(); fetchContainerHistory(); }}
          className="flex items-center gap-2 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 dark:hover:bg-gray-700/50">
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 rounded-lg p-3 text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
        <button onClick={() => setTab('iac')}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors flex items-center gap-2 ${tab === 'iac' ? 'border-blue-500 text-blue-600 dark:text-blue-400' : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}`}>
          <FileCode className="w-4 h-4" /> IaC Scanner
        </button>
        <button onClick={() => setTab('container')}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors flex items-center gap-2 ${tab === 'container' ? 'border-blue-500 text-blue-600 dark:text-blue-400' : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}`}>
          <Server className="w-4 h-4" /> Container Scanner
        </button>
      </div>

      {/* ── IaC Scanner Tab ────────────────────────────────────────────── */}
      {tab === 'iac' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left: input */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
              <span className="text-sm font-semibold text-gray-900 dark:text-white">Code Input</span>
              <label className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-800 rounded-md cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900/20">
                <Upload className="w-3.5 h-3.5" /> Upload File
                <input type="file" accept=".tf,.yaml,.yml,.json" onChange={handleFileUpload} className="hidden" />
              </label>
            </div>
            <div className="p-4 space-y-3">
              <select value={iacFilename} onChange={e => setIacFilename(e.target.value)}
                className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg">
                <option value="main.tf">main.tf (Terraform)</option>
                <option value="deployment.yaml">deployment.yaml (K8s)</option>
                <option value="template.yaml">template.yaml (CloudFormation)</option>
              </select>
              <textarea value={iacCode} onChange={e => setIacCode(e.target.value)}
                placeholder={'Paste Terraform / K8s / CloudFormation code here...\n\ne.g.\nresource "aws_s3_bucket" "data" {\n  bucket = "my-bucket"\n  acl    = "public-read"\n}'}
                className="w-full min-h-[240px] px-3 py-2 text-xs font-mono border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-y" />
              <button onClick={runIacScan} disabled={loading || !iacCode.trim()}
                className="flex items-center gap-2 px-4 py-2 text-sm font-semibold bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed">
                <Terminal className="w-4 h-4" /> {loading ? 'Scanning...' : 'Scan Code'}
              </button>
            </div>
          </div>

          {/* Right: results */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
              <span className="text-sm font-semibold text-gray-900 dark:text-white">Scan Results</span>
              {iacResult && !iacResult.warning && (
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {iacResult.total - iacResult.fail} pass · {iacResult.fail} fail · {iacResult.total} checks
                </span>
              )}
            </div>
            <div className="p-4">
              {loading ? (
                <Spinner />
              ) : !iacResult ? (
                <div className="text-center text-gray-400 dark:text-gray-500 py-10">
                  <Shield className="w-8 h-8 mx-auto mb-2 opacity-40" />
                  <p className="text-sm font-medium text-gray-500 dark:text-gray-400">No scan run yet</p>
                  <p className="text-xs mt-1 max-w-xs mx-auto">Paste Terraform, CloudFormation, or Kubernetes YAML on the left and click Scan Code to check for misconfigurations.</p>
                </div>
              ) : iacResult.warning ? (
                <div className="px-3 py-2 bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400 rounded-lg text-sm flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0" /> {iacResult.warning}
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
                    <thead className="bg-gray-50 dark:bg-gray-900/50">
                      <tr>
                        {['Check', 'Severity', 'Status', 'Line', 'Message'].map(h => (
                          <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                      {sortedFindings.map((r, i) => (
                        <tr key={i} className={r.status.toUpperCase() === 'FAIL' ? 'bg-red-50/50 dark:bg-red-900/10' : ''}>
                          <td className="px-4 py-3 font-mono text-xs font-medium text-gray-900 dark:text-white">{r.check_id}</td>
                          <td className="px-4 py-3"><span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${SEV_COLORS[(r.severity || '').toLowerCase()] || SEV_FALLBACK}`}>{r.severity}</span></td>
                          <td className="px-4 py-3"><span className={statusBadgeClass(r.status)}>{r.status.toUpperCase() === 'FAIL' ? <XCircle className="w-3 h-3" /> : <CheckCircle className="w-3 h-3" />} {r.status.toUpperCase()}</span></td>
                          <td className="px-4 py-3 font-mono text-xs text-gray-500 dark:text-gray-400">{r.line ?? '—'}</td>
                          <td className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400">{r.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>

          {/* History */}
          <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
              <span className="text-sm font-semibold text-gray-900 dark:text-white">Scan History</span>
            </div>
            <div className="p-4 space-y-2">
              {iacHistory.length === 0 ? (
                <p className="text-xs text-gray-400 dark:text-gray-500 italic">No scans yet — results will appear here after your first scan.</p>
              ) : (
                iacHistory.map((h, i) => (
                  <div key={i} className="flex items-center gap-3 px-3 py-2 bg-gray-50 dark:bg-gray-900/40 rounded-lg text-xs">
                    <FileCode className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                    <span className="font-mono font-medium text-gray-700 dark:text-gray-300">{h.scan_id}</span>
                    <span className="px-1.5 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded">{h.provider}</span>
                    <span className="text-green-600 dark:text-green-400">{h.total - h.fail} pass</span>
                    {h.fail > 0 && <span className="text-red-600 dark:text-red-400">{h.fail} fail</span>}
                    <span className="ml-auto text-gray-400 dark:text-gray-500">{timeAgo(h.scanned_at)}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Container Scanner Tab ───────────────────────────────────────── */}
      {tab === 'container' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left: input */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
              <span className="text-sm font-semibold text-gray-900 dark:text-white">Scan Image</span>
            </div>
            <div className="p-4 space-y-3">
              <div className="flex gap-2">
                <input value={imageName} onChange={e => setImageName(e.target.value)}
                  placeholder="nginx:latest"
                  className="flex-1 px-3 py-2 text-sm font-mono border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
                <button onClick={runContainerScan} disabled={loading || !imageName.trim()}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-semibold bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap">
                  <Terminal className="w-4 h-4" /> {loading ? 'Scanning...' : 'Scan Image'}
                </button>
              </div>
              {containerResult?.note && (
                <div className="px-3 py-2 bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400 rounded-lg text-xs flex items-center gap-2">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0" /> {containerResult.note}
                </div>
              )}
            </div>
          </div>

          {/* Right: summary */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
              <span className="text-sm font-semibold text-gray-900 dark:text-white">Vulnerability Summary</span>
            </div>
            <div className="p-4">
              {loading ? (
                <Spinner />
              ) : !containerResult ? (
                <div className="text-center text-gray-400 dark:text-gray-500 py-10">
                  <Server className="w-8 h-8 mx-auto mb-2 opacity-40" />
                  <p className="text-sm font-medium text-gray-500 dark:text-gray-400">No image scanned yet</p>
                  <p className="text-xs mt-1 max-w-xs mx-auto">Enter an image name (e.g. <code className="font-mono">nginx:latest</code>) and click Scan Image to check for known vulnerabilities.</p>
                </div>
              ) : (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">{containerResult.image}</p>
                    {containerResult.simulated && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400 rounded-full text-xs font-semibold">
                        <AlertTriangle className="w-3 h-3 shrink-0" /> SIMULATED — not a real Trivy scan
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-4 gap-3">
                    {[
                      { label: 'Total', value: containerResult.total, className: 'text-gray-900 dark:text-white' },
                      { label: 'Critical', value: containerResult.critical, className: 'text-red-600 dark:text-red-400' },
                      { label: 'High', value: containerResult.high, className: 'text-orange-600 dark:text-orange-400' },
                      { label: 'Medium', value: containerResult.medium, className: 'text-yellow-600 dark:text-yellow-400' },
                    ].map(s => (
                      <div key={s.label} className="text-center bg-gray-50 dark:bg-gray-900/50 rounded-lg p-3">
                        <p className={`text-2xl font-bold ${s.className}`}>{s.value}</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{s.label}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Vulns table */}
          {containerResult && containerResult.vulns.length > 0 && (
            <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
                <span className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                  Vulnerabilities
                  {containerResult.simulated && (
                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400 rounded text-xs font-semibold">
                      <AlertTriangle className="w-3 h-3 shrink-0" /> SIMULATED
                    </span>
                  )}
                </span>
                <span className="text-xs text-gray-500 dark:text-gray-400">{containerResult.vulns.length} findings</span>
              </div>
              <div className="p-4 overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
                  <thead className="bg-gray-50 dark:bg-gray-900/50">
                    <tr>
                      {['CVE', 'Package', 'Severity', 'Installed', 'Fixed', 'Title'].map(h => (
                        <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                    {containerResult.vulns.map((v, i) => (
                      <tr key={i}>
                        <td className="px-4 py-3 font-mono text-xs font-medium text-gray-900 dark:text-white">{v.id}</td>
                        <td className="px-4 py-3 font-medium text-gray-700 dark:text-gray-300">{v.pkg_name}</td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${SEV_COLORS[(v.severity || '').toLowerCase()] || SEV_FALLBACK}`}>{v.severity}</span>
                        </td>
                        <td className="px-4 py-3 font-mono text-xs text-gray-500 dark:text-gray-400">{v.installed_version}</td>
                        <td className="px-4 py-3 font-mono text-xs">{v.fixed_version ? <span className="text-green-600 dark:text-green-400">{v.fixed_version}</span> : <span className="text-gray-400 dark:text-gray-500">—</span>}</td>
                        <td className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400 max-w-xs truncate">{v.title}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Container history */}
          <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
              <span className="text-sm font-semibold text-gray-900 dark:text-white">Scan History</span>
            </div>
            <div className="p-4 space-y-2">
              {containerHistory.length === 0 ? (
                <p className="text-xs text-gray-400 dark:text-gray-500 italic">No scans yet — results will appear here after your first scan.</p>
              ) : (
                containerHistory.map((h, i) => (
                  <div key={i} className="flex items-center gap-3 px-3 py-2 bg-gray-50 dark:bg-gray-900/40 rounded-lg text-xs">
                    <Server className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                    <span className="font-mono font-medium text-gray-700 dark:text-gray-300">{h.image}</span>
                    {h.simulated && <span className="px-1.5 py-0.5 bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 rounded">sim</span>}
                    <span className="text-red-600 dark:text-red-400">{h.critical} critical</span>
                    <span className="text-orange-600 dark:text-orange-400">{h.high} high</span>
                    <span className="text-gray-500 dark:text-gray-400">{h.total} total</span>
                    <span className="ml-auto text-gray-400 dark:text-gray-500">{timeAgo(h.scanned_at)}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default IacContainerDashboard;
