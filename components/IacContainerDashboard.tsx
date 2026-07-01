import React, { useState, useCallback, useEffect } from 'react';
import { Shield, AlertTriangle, CheckCircle, RefreshCw, Upload, Terminal, Server, FileCode } from 'lucide-react';

interface IaCResult {
  check_id: string;
  name: string;
  severity: string;
  status: string;
  message: string;
  line_ref: number | null;
}

interface IaCScanResponse {
  scan_id: string;
  filename: string;
  type: string;
  scanned_at: string;
  total_checks: number;
  pass_count: number;
  fail_count: number;
  results: IaCResult[];
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

const SEV_COLOR: Record<string, string> = {
  critical: '#fca5a5', high: '#fcd34d', medium: '#a5b4fc', low: '#94a3b8',
  CRITICAL: '#fca5a5', HIGH: '#fcd34d', MEDIUM: '#a5b4fc', LOW: '#94a3b8', UNKNOWN: '#6b7280',
};

function timeAgo(ts: string) {
  const d = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (d < 60) return `${Math.max(0, d)}s ago`;
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  return `${Math.floor(d / 3600)}h ago`;
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
    const r = await fetch('/api/iac/results', { headers }).then(r => r.ok ? r.json() : null);
    if (r) setIacHistory(r.items || []);
  }, []);

  const fetchContainerHistory = useCallback(async () => {
    const r = await fetch('/api/container/results', { headers }).then(r => r.ok ? r.json() : null);
    if (r) setContainerHistory(r.items || []);
  }, []);

  const fetchIacConfig = useCallback(async () => {
    const r = await fetch('/api/iac/scan-config', { headers }).then(r => r.ok ? r.json() : null);
    if (r) setIacConfig(r.config);
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
      if (!r.ok) { setError(`IaC scan failed (${r.status})`); return; }
      const data: IaCScanResponse = await r.json();
      setIacResult(data);
      fetchIacHistory();
    } catch (e: any) { setError(e.message); }
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
      if (!r.ok) { setError(`Container scan failed (${r.status})`); return; }
      const data: ContainerScanResponse = await r.json();
      setContainerResult(data);
      fetchContainerHistory();
    } catch (e: any) { setError(e.message); }
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

  const TAB_STYLE = (active: boolean) => ({
    padding: '10px 22px', cursor: 'pointer', fontSize: '0.82em', fontWeight: 700,
    borderRadius: '8px 8px 0 0', border: 'none', background: active ? 'rgba(99,102,241,.2)' : 'transparent',
    color: active ? '#a5b4fc' : '#64748b', borderBottom: active ? '2px solid #6366f1' : '2px solid transparent',
    transition: 'all .15s',
  });

  const BADGE = (status: string) => {
    const isFail = status === 'fail' || status === 'FAIL';
    return {
      display: 'inline-flex', alignItems: 'center', gap: 4,
      background: isFail ? 'rgba(239,68,68,.15)' : 'rgba(16,185,129,.12)',
      color: isFail ? '#fca5a5' : '#6ee7b7',
      borderRadius: 20, padding: '3px 10px', fontSize: '0.72em', fontWeight: 700,
    } as const;
  };

  const CELL = { padding: '10px 14px', fontSize: '0.78em', borderBottom: '1px solid rgba(255,255,255,.04)' } as const;

  return (
    <div style={{ padding: '28px 32px', color: '#f1f5f9', fontFamily: 'Inter, sans-serif', minHeight: '100vh', background: '#040812' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: '0.72em', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6366f1', marginBottom: 6 }}>DevSecOps</div>
          <h1 style={{ fontSize: '1.8em', fontWeight: 900, letterSpacing: '-0.03em', margin: 0 }}>IaC & Container Security</h1>
          <p style={{ color: '#94a3b8', fontSize: '0.85em', marginTop: 4 }}>Infrastructure-as-Code scanning · Container vulnerability analysis</p>
        </div>
        <button onClick={() => { setTab('iac'); fetchIacHistory(); fetchContainerHistory(); }}
          style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(99,102,241,.15)', border: '1px solid rgba(99,102,241,.3)', color: '#a5b4fc', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: '0.82em' }}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 0, borderBottom: '1px solid rgba(255,255,255,.07)' }}>
        <button style={TAB_STYLE(tab === 'iac')} onClick={() => setTab('iac')}>
          <FileCode size={14} style={{ marginRight: 6, verticalAlign: 'middle' }} /> IaC Scanner
        </button>
        <button style={TAB_STYLE(tab === 'container')} onClick={() => setTab('container')}>
          <Server size={14} style={{ marginRight: 6, verticalAlign: 'middle' }} /> Container Scanner
        </button>
      </div>

      {error && (
        <div style={{ marginTop: 16, padding: '10px 16px', background: 'rgba(239,68,68,.12)', borderRadius: 8, color: '#fca5a5', fontSize: '0.82em' }}>
          <AlertTriangle size={13} style={{ marginRight: 6, verticalAlign: 'middle' }} /> {error}
        </div>
      )}

      {/* ── IaC Scanner Tab ────────────────────────────────────────────── */}
      {tab === 'iac' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginTop: 20 }}>
          {/* Left: input */}
          <div style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, overflow: 'hidden' }}>
            <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,.07)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 700, fontSize: '0.9em' }}>Code Input</span>
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'rgba(99,102,241,.12)', border: '1px solid rgba(99,102,241,.25)', color: '#a5b4fc', borderRadius: 6, padding: '5px 12px', cursor: 'pointer', fontSize: '0.75em', fontWeight: 600 }}>
                <Upload size={12} /> Upload File
                <input type="file" accept=".tf,.yaml,.yml,.json" onChange={handleFileUpload} style={{ display: 'none' }} />
              </label>
            </div>
            <div style={{ padding: 14 }}>
              <div style={{ display: 'flex', gap: 10, marginBottom: 12, alignItems: 'center' }}>
                <select value={iacFilename} onChange={e => setIacFilename(e.target.value)}
                  style={{ background: 'rgba(0,0,0,.3)', color: '#94a3b8', border: '1px solid rgba(255,255,255,.1)', borderRadius: 6, padding: '6px 10px', fontSize: '0.78em' }}>
                  <option value="main.tf">main.tf (Terraform)</option>
                  <option value="deployment.yaml">deployment.yaml (K8s)</option>
                  <option value="template.yaml">template.yaml (CloudFormation)</option>
                </select>
              </div>
              <textarea value={iacCode} onChange={e => setIacCode(e.target.value)}
                placeholder={'Paste Terraform / K8s / CloudFormation code here...\n\ne.g.\nresource "aws_s3_bucket" "data" {\n  bucket = "my-bucket"\n  acl    = "public-read"\n}'}
                style={{ width: '100%', minHeight: 240, background: 'rgba(0,0,0,.3)', color: '#e2e8f0', border: '1px solid rgba(255,255,255,.08)', borderRadius: 8, padding: 12, fontSize: '0.82em', fontFamily: 'monospace', resize: 'vertical' }} />
              <button onClick={runIacScan} disabled={loading || !iacCode.trim()}
                style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 6, background: loading ? 'rgba(99,102,241,.3)' : 'rgba(99,102,241,.2)', border: '1px solid rgba(99,102,241,.4)', color: loading ? '#94a3b8' : '#a5b4fc', borderRadius: 8, padding: '10px 20px', cursor: loading ? 'not-allowed' : 'pointer', fontSize: '0.82em', fontWeight: 700 }}>
                <Terminal size={14} /> {loading ? 'Scanning...' : 'Scan Code'}
              </button>
            </div>
          </div>

          {/* Right: results */}
          <div style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, overflow: 'hidden' }}>
            <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,.07)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 700, fontSize: '0.9em' }}>Scan Results</span>
              {iacResult && (
                <span style={{ fontSize: '0.75em', color: '#94a3b8' }}>
                  {iacResult.pass_count} pass · {iacResult.fail_count} fail · {iacResult.total_checks} checks
                </span>
              )}
            </div>
            <div style={{ padding: 14 }}>
              {!iacResult ? (
                <div style={{ textAlign: 'center', color: '#94a3b8', padding: 40, fontSize: '0.85em' }}>
                  <Shield size={32} style={{ margin: '0 auto 10px', opacity: 0.4 }} />
                  <div>Paste code and click Scan to check for misconfigurations</div>
                </div>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ color: '#64748b', fontSize: '0.72em', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                        <th style={CELL}>Check</th>
                        <th style={CELL}>Severity</th>
                        <th style={CELL}>Status</th>
                        <th style={CELL}>Line</th>
                        <th style={CELL}>Message</th>
                      </tr>
                    </thead>
                    <tbody>
                      {iacResult.results.map((r, i) => (
                        <tr key={i} style={{ background: r.status === 'fail' ? 'rgba(239,68,68,.03)' : 'transparent' }}>
                          <td style={{ ...CELL, fontWeight: 600, fontFamily: 'monospace', fontSize: '0.72em' }}>{r.check_id}</td>
                          <td style={{ ...CELL, color: SEV_COLOR[r.severity] || '#94a3b8', fontWeight: 600 }}>{r.severity.toUpperCase()}</td>
                          <td style={CELL}><span style={BADGE(r.status)}>{r.status === 'fail' ? <AlertTriangle size={11} /> : <CheckCircle size={11} />} {r.status.toUpperCase()}</span></td>
                          <td style={{ ...CELL, color: '#64748b', fontFamily: 'monospace' }}>{r.line_ref ?? '—'}</td>
                          <td style={{ ...CELL, color: '#cbd5e1', fontSize: '0.74em' }}>{r.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>

          {/* History */}
          {iacHistory.length > 0 && (
            <div style={{ gridColumn: '1 / -1', background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,.07)' }}>
                <span style={{ fontWeight: 700, fontSize: '0.9em' }}>Scan History</span>
              </div>
              <div style={{ padding: 14 }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {iacHistory.map((h, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', background: 'rgba(255,255,255,.02)', borderRadius: 8 }}>
                      <FileCode size={14} color="#94a3b8" />
                      <span style={{ fontSize: '0.78em', color: '#cbd5e1', fontWeight: 600 }}>{h.filename}</span>
                      <span style={{ fontSize: '0.72em', color: SEV_COLOR[h.type], background: `${SEV_COLOR[h.type]}15`, borderRadius: 4, padding: '1px 6px' }}>{h.type}</span>
                      <span style={{ fontSize: '0.72em', color: '#6ee7b7' }}>{h.pass_count} pass</span>
                      {h.fail_count > 0 && <span style={{ fontSize: '0.72em', color: '#fca5a5' }}>{h.fail_count} fail</span>}
                      <span style={{ marginLeft: 'auto', fontSize: '0.72em', color: '#64748b' }}>{timeAgo(h.scanned_at)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Container Scanner Tab ───────────────────────────────────────── */}
      {tab === 'container' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginTop: 20 }}>
          {/* Left: input */}
          <div style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, overflow: 'hidden' }}>
            <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,.07)' }}>
              <span style={{ fontWeight: 700, fontSize: '0.9em' }}>Scan Image</span>
            </div>
            <div style={{ padding: 14 }}>
              <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
                <input value={imageName} onChange={e => setImageName(e.target.value)}
                  placeholder="nginx:latest"
                  style={{ flex: 1, background: 'rgba(0,0,0,.3)', color: '#e2e8f0', border: '1px solid rgba(255,255,255,.08)', borderRadius: 8, padding: '10px 14px', fontSize: '0.88em', fontFamily: 'monospace' }} />
                <button onClick={runContainerScan} disabled={loading || !imageName.trim()}
                  style={{ display: 'flex', alignItems: 'center', gap: 6, background: loading ? 'rgba(99,102,241,.3)' : 'rgba(99,102,241,.2)', border: '1px solid rgba(99,102,241,.4)', color: loading ? '#94a3b8' : '#a5b4fc', borderRadius: 8, padding: '10px 20px', cursor: loading ? 'not-allowed' : 'pointer', fontSize: '0.82em', fontWeight: 700, whiteSpace: 'nowrap' }}>
                  <Terminal size={14} /> {loading ? 'Scanning...' : 'Scan'}
                </button>
              </div>
              {containerResult?.note && (
                <div style={{ padding: '8px 12px', background: 'rgba(245,158,11,.1)', borderRadius: 6, color: '#fcd34d', fontSize: '0.75em', marginTop: 8 }}>
                  <AlertTriangle size={11} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                  {containerResult.note}
                </div>
              )}
            </div>
          </div>

          {/* Right: summary */}
          <div style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, overflow: 'hidden' }}>
            <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,.07)' }}>
              <span style={{ fontWeight: 700, fontSize: '0.9em' }}>Vulnerability Summary</span>
            </div>
            <div style={{ padding: 14 }}>
              {!containerResult ? (
                <div style={{ textAlign: 'center', color: '#94a3b8', padding: 40, fontSize: '0.85em' }}>
                  <Server size={32} style={{ margin: '0 auto 10px', opacity: 0.4 }} />
                  <div>Enter an image name and click Scan</div>
                </div>
              ) : (
                <div>
                  <div style={{ fontSize: '0.82em', color: '#94a3b8', marginBottom: 12 }}>{containerResult.image}</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 16 }}>
                    {[
                      { label: 'Total', value: containerResult.total, color: '#a5b4fc' },
                      { label: 'Critical', value: containerResult.critical, color: '#fca5a5' },
                      { label: 'High', value: containerResult.high, color: '#fcd34d' },
                      { label: 'Medium', value: containerResult.medium, color: '#a5b4fc' },
                    ].map(s => (
                      <div key={s.label} style={{ textAlign: 'center', background: 'rgba(255,255,255,.03)', borderRadius: 8, padding: '12px 8px' }}>
                        <div style={{ fontSize: '1.4em', fontWeight: 900, color: s.color }}>{s.value}</div>
                        <div style={{ fontSize: '0.68em', color: '#64748b', marginTop: 2 }}>{s.label}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Vulns table */}
          {containerResult && containerResult.vulns.length > 0 && (
            <div style={{ gridColumn: '1 / -1', background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,.07)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 700, fontSize: '0.9em' }}>Vulnerabilities</span>
                <span style={{ fontSize: '0.72em', color: '#94a3b8' }}>{containerResult.vulns.length} findings</span>
              </div>
              <div style={{ padding: 14, overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ color: '#64748b', fontSize: '0.72em', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                      <th style={CELL}>CVE</th>
                      <th style={CELL}>Package</th>
                      <th style={CELL}>Severity</th>
                      <th style={CELL}>Installed</th>
                      <th style={CELL}>Fixed</th>
                      <th style={CELL}>Title</th>
                    </tr>
                  </thead>
                  <tbody>
                    {containerResult.vulns.map((v, i) => (
                      <tr key={i}>
                        <td style={{ ...CELL, fontFamily: 'monospace', fontSize: '0.72em', fontWeight: 600, color: '#e2e8f0' }}>{v.id}</td>
                        <td style={{ ...CELL, fontWeight: 600, color: '#cbd5e1' }}>{v.pkg_name}</td>
                        <td style={CELL}>
                          <span style={{ color: SEV_COLOR[v.severity] || '#94a3b8', fontWeight: 700, fontSize: '0.72em', background: `${(SEV_COLOR[v.severity] || '#94a3b8')}15`, borderRadius: 4, padding: '2px 7px' }}>
                            {v.severity}
                          </span>
                        </td>
                        <td style={{ ...CELL, color: '#64748b', fontFamily: 'monospace', fontSize: '0.72em' }}>{v.installed_version}</td>
                        <td style={{ ...CELL, color: v.fixed_version ? '#6ee7b7' : '#64748b', fontFamily: 'monospace', fontSize: '0.72em' }}>{v.fixed_version || '—'}</td>
                        <td style={{ ...CELL, color: '#94a3b8', fontSize: '0.72em', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v.title}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Container history */}
          {containerHistory.length > 0 && (
            <div style={{ gridColumn: '1 / -1', background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,.07)' }}>
                <span style={{ fontWeight: 700, fontSize: '0.9em' }}>Scan History</span>
              </div>
              <div style={{ padding: 14 }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {containerHistory.map((h, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', background: 'rgba(255,255,255,.02)', borderRadius: 8 }}>
                      <Server size={14} color="#94a3b8" />
                      <span style={{ fontSize: '0.78em', color: '#cbd5e1', fontWeight: 600, fontFamily: 'monospace' }}>{h.image}</span>
                      <span style={{ fontSize: '0.72em', color: '#fca5a5' }}>{h.critical} critical</span>
                      <span style={{ fontSize: '0.72em', color: '#fcd34d' }}>{h.high} high</span>
                      <span style={{ fontSize: '0.72em', color: '#94a3b8' }}>{h.total} total</span>
                      <span style={{ marginLeft: 'auto', fontSize: '0.72em', color: '#64748b' }}>{timeAgo(h.scanned_at)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default IacContainerDashboard;
