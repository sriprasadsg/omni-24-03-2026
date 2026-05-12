import React, { useState, useEffect, useCallback } from 'react';
import { GitBranch, Shield, XCircle, AlertTriangle, CheckCircle, RefreshCw, Play, Lock } from 'lucide-react';

interface PipelineScan {
  id: string;
  repo: string;
  branch: string;
  pipeline: string;
  status: 'passed' | 'failed' | 'blocked' | 'queued';
  scanned_at: number;
  findings: Finding[];
}

interface Finding {
  type: 'secret_leak' | 'iac_violation' | 'dependency_risk';
  severity: 'critical' | 'high' | 'medium' | 'low';
  file?: string;
  line?: number;
  message?: string;
  package?: string;
  cve?: string;
  rule?: string;
  secret_type?: string;
}

interface Stats {
  total_scans: number;
  passed: number;
  failed: number;
  blocked: number;
  secret_leaks_blocked: number;
  iac_violations: number;
  dependency_risks: number;
}

function timeAgo(ts: number) {
  const d = Date.now() / 1000 - ts;
  if (d < 60) return `${Math.round(d)}s ago`;
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  return `${Math.round(d / 3600)}h ago`;
}

const STATUS_STYLES: Record<string, { bg: string; color: string; icon: React.ReactNode }> = {
  passed: { bg: 'rgba(16,185,129,.12)', color: '#6ee7b7', icon: <CheckCircle size={12} /> },
  failed: { bg: 'rgba(239,68,68,.12)', color: '#fca5a5', icon: <XCircle size={12} /> },
  blocked: { bg: 'rgba(245,158,11,.12)', color: '#fcd34d', icon: <Lock size={12} /> },
  queued: { bg: 'rgba(148,163,184,.1)', color: '#94a3b8', icon: <RefreshCw size={12} /> },
};

const SEV_COLOR: Record<string, string> = {
  critical: '#fca5a5', high: '#fcd34d', medium: '#a5b4fc', low: '#94a3b8',
};

export function PipelineSecurityDashboard() {
  const [scans, setScans] = useState<PipelineScan[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<PipelineScan | null>(null);

  const token = localStorage.getItem('access_token');
  const headers = token ? { Authorization: `Bearer ${token}` } : {};

  const fetchAll = useCallback(async () => {
    setLoading(true);
    const [s1, s2] = await Promise.all([
      fetch('/api/pipeline-security/scans', { headers }).then(r => r.ok ? r.json() : []),
      fetch('/api/pipeline-security/stats', { headers }).then(r => r.ok ? r.json() : null),
    ]).catch(() => [[], null]);
    setScans(Array.isArray(s1) ? s1 : []);
    setStats(s2);
    setLoading(false);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const st = stats;

  return (
    <div style={{ padding: '28px 32px', color: '#f1f5f9', fontFamily: 'Inter, sans-serif', minHeight: '100vh', background: '#040812' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <div>
          <div style={{ fontSize: '0.72em', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6366f1', marginBottom: 6 }}>DevSecOps</div>
          <h1 style={{ fontSize: '1.8em', fontWeight: 900, letterSpacing: '-0.03em', margin: 0 }}>Pipeline Security</h1>
          <p style={{ color: '#94a3b8', fontSize: '0.85em', marginTop: 4 }}>Secret scanning · IaC policy gates · Dependency risk · CI/CD security enforcement</p>
        </div>
        <button onClick={fetchAll} style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(99,102,241,.15)', border: '1px solid rgba(99,102,241,.3)', color: '#a5b4fc', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: '0.82em' }}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {/* Stats */}
      {st && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 14, marginBottom: 28 }}>
          {[
            { label: 'Total Scans', value: st.total_scans, color: '#a5b4fc' },
            { label: 'Passed', value: st.passed, color: '#6ee7b7' },
            { label: 'Failed', value: st.failed, color: '#fca5a5' },
            { label: 'Blocked', value: st.blocked, color: '#fcd34d' },
            { label: 'Secrets Blocked', value: st.secret_leaks_blocked, color: '#fca5a5' },
            { label: 'IaC Violations', value: st.iac_violations, color: '#fcd34d' },
            { label: 'Dep. Risks', value: st.dependency_risks, color: '#a5b4fc' },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 12, padding: '16px 18px', textAlign: 'center' }}>
              <div style={{ fontSize: '1.8em', fontWeight: 900, color }}>{value}</div>
              <div style={{ fontSize: '0.72em', color: '#94a3b8', marginTop: 4 }}>{label}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: 20 }}>
        {/* Scan list */}
        <div style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, overflow: 'hidden' }}>
          <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,.07)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 700, fontSize: '0.9em' }}>Recent Scans</span>
            <span style={{ fontSize: '0.75em', color: '#94a3b8' }}>{scans.length} results</span>
          </div>
          {loading ? <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>Loading…</div> : (
            <div>
              {scans.map(scan => {
                const ss = STATUS_STYLES[scan.status] || STATUS_STYLES.queued;
                return (
                  <div key={scan.id} onClick={() => setSelected(scan === selected ? null : scan)}
                    style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,.04)', cursor: 'pointer', background: selected?.id === scan.id ? 'rgba(99,102,241,.08)' : 'transparent' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <GitBranch size={14} color="#94a3b8" />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600, fontSize: '0.88em' }}>{scan.repo}</div>
                        <div style={{ fontSize: '0.75em', color: '#64748b' }}>{scan.branch} · {scan.pipeline} · {timeAgo(scan.scanned_at)}</div>
                      </div>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, background: ss.bg, color: ss.color, borderRadius: 20, padding: '3px 10px', fontSize: '0.72em', fontWeight: 700 }}>
                        {ss.icon} {scan.status}
                      </span>
                      {scan.findings.length > 0 && (
                        <span style={{ fontSize: '0.72em', color: '#fca5a5', background: 'rgba(239,68,68,.1)', borderRadius: 20, padding: '2px 8px' }}>
                          {scan.findings.length} finding{scan.findings.length !== 1 ? 's' : ''}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Finding detail */}
        <div style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, overflow: 'hidden' }}>
          <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,.07)' }}>
            <span style={{ fontWeight: 700, fontSize: '0.9em' }}>{selected ? `Findings — ${selected.repo}` : 'Select a scan'}</span>
          </div>
          <div style={{ padding: 16 }}>
            {!selected ? (
              <div style={{ textAlign: 'center', color: '#94a3b8', padding: 40, fontSize: '0.85em' }}>Click a scan to view findings</div>
            ) : selected.findings.length === 0 ? (
              <div style={{ textAlign: 'center', color: '#6ee7b7', padding: 40 }}>
                <CheckCircle size={32} style={{ margin: '0 auto 10px' }} />
                <div style={{ fontWeight: 600 }}>No findings</div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {selected.findings.map((f, i) => (
                  <div key={i} style={{ background: 'rgba(255,255,255,.04)', border: `1px solid ${SEV_COLOR[f.severity]}30`, borderRadius: 10, padding: '12px 14px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                      <span style={{ fontSize: '0.7em', fontWeight: 700, color: SEV_COLOR[f.severity], background: `${SEV_COLOR[f.severity]}15`, borderRadius: 20, padding: '2px 8px' }}>{f.severity.toUpperCase()}</span>
                      <span style={{ fontSize: '0.75em', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase' }}>{f.type.replace('_', ' ')}</span>
                    </div>
                    <div style={{ fontSize: '0.8em', color: '#f1f5f9', fontWeight: 600, marginBottom: 4 }}>
                      {f.rule || f.cve || f.secret_type || f.package || 'Unknown'}
                    </div>
                    {f.file && <div style={{ fontSize: '0.72em', color: '#64748b', fontFamily: 'monospace' }}>{f.file}{f.line ? `:${f.line}` : ''}</div>}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default PipelineSecurityDashboard;
