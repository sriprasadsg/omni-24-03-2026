import React, { useState, useEffect, useCallback } from 'react';
import { Code2, AlertTriangle, XCircle, CheckCircle, RefreshCw, EyeOff } from 'lucide-react';
import { showToast } from '../utils/toast';

interface Violation {
  id: string;
  scan_id: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  file: string;
  line: number;
  rule: string;
  message: string;
  resource: string;
  provider: string;
  suppressed: boolean;
}

interface IaCStats {
  total_violations: number;
  critical: number;
  high: number;
  medium: number;
  suppressed: number;
  frameworks_checked: string[];
  rules_applied: number;
}

const SEV_COLOR: Record<string, string> = {
  critical: '#fca5a5', high: '#fcd34d', medium: '#a5b4fc', low: '#94a3b8',
};
const PROVIDER_COLOR: Record<string, string> = {
  aws: '#ff9900', kubernetes: '#326ce5', cloudformation: '#ff9900', azure: '#0078d4', gcp: '#4285f4',
};

export function IaCSecurityDashboard() {
  const [violations, setViolations] = useState<Violation[]>([]);
  const [stats, setStats] = useState<IaCStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('all');
  const [suppressing, setSuppressing] = useState<string | null>(null);

  const token = sessionStorage.getItem('access_token');
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const fetchAll = useCallback(async () => {
    setLoading(true);
    const [v, s] = await Promise.all([
      fetch('/api/iac-security/violations', { headers }).then(r => r.ok ? r.json() : []),
      fetch('/api/iac-security/stats', { headers }).then(r => r.ok ? r.json() : null),
    ]).catch(() => [[], null]);
    setViolations(Array.isArray(v) ? v : []);
    setStats(s);
    setLoading(false);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const suppress = useCallback(async (id: string) => {
    setSuppressing(id);
    try {
      const res = await fetch(`/api/iac-security/violations/${id}/suppress`, {
        method: 'POST', headers, body: JSON.stringify({ reason: 'Accepted risk' }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? 'Suppress failed');
      setViolations(prev => prev.map(v => v.id === id ? { ...v, suppressed: true } : v));
    } catch (e) {
      console.error('IaC violation suppress failed:', e);
      showToast(e instanceof Error ? e.message : 'Failed to suppress violation', 'error');
    }
    setSuppressing(null);
  }, []);

  const filtered = filter === 'all' ? violations.filter(v => !v.suppressed)
    : filter === 'suppressed' ? violations.filter(v => v.suppressed)
    : violations.filter(v => !v.suppressed && v.severity === filter);

  return (
    <div style={{ padding: '28px 32px', color: '#f1f5f9', fontFamily: 'Inter, sans-serif', minHeight: '100vh', background: '#040812' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <div>
          <div style={{ fontSize: '0.72em', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6366f1', marginBottom: 6 }}>DevSecOps</div>
          <h1 style={{ fontSize: '1.8em', fontWeight: 900, letterSpacing: '-0.03em', margin: 0 }}>IaC Security</h1>
          <p style={{ color: '#94a3b8', fontSize: '0.85em', marginTop: 4 }}>Terraform · CloudFormation · Kubernetes YAML · Helm — static policy validation</p>
        </div>
        <button onClick={fetchAll} style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(99,102,241,.15)', border: '1px solid rgba(99,102,241,.3)', color: '#a5b4fc', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: '0.82em' }}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 14, marginBottom: 28 }}>
          {[
            { label: 'Total', value: stats.total_violations, color: '#a5b4fc' },
            { label: 'Critical', value: stats.critical, color: '#fca5a5' },
            { label: 'High', value: stats.high, color: '#fcd34d' },
            { label: 'Medium', value: stats.medium, color: '#a5b4fc' },
            { label: 'Suppressed', value: stats.suppressed, color: '#94a3b8' },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 12, padding: '16px', textAlign: 'center' }}>
              <div style={{ fontSize: '2em', fontWeight: 900, color }}>{value}</div>
              <div style={{ fontSize: '0.72em', color: '#94a3b8', marginTop: 4 }}>{label}</div>
            </div>
          ))}
        </div>
      )}

      {stats && (
        <div style={{ display: 'flex', gap: 10, marginBottom: 20, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: '0.78em', color: '#94a3b8' }}>Frameworks: </span>
          {stats.frameworks_checked?.map(f => (
            <span key={f} style={{ background: 'rgba(99,102,241,.12)', border: '1px solid rgba(99,102,241,.25)', color: '#a5b4fc', borderRadius: 6, padding: '3px 10px', fontSize: '0.75em', fontWeight: 600 }}>{f}</span>
          ))}
          <span style={{ marginLeft: 'auto', fontSize: '0.78em', color: '#94a3b8' }}>{stats.rules_applied} rules applied</span>
        </div>
      )}

      {/* Filter buttons */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {['all', 'critical', 'high', 'medium', 'low', 'suppressed'].map(f => (
          <button key={f} onClick={() => setFilter(f)} style={{
            background: filter === f ? 'rgba(99,102,241,.2)' : 'transparent',
            border: '1px solid rgba(255,255,255,.1)', color: filter === f ? '#a5b4fc' : '#94a3b8',
            borderRadius: 6, padding: '5px 14px', cursor: 'pointer', fontSize: '0.78em', fontWeight: 600, textTransform: 'capitalize',
          }}>{f}</button>
        ))}
      </div>

      {/* Violations table */}
      <div style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, overflow: 'hidden' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '90px 80px 1fr 160px 100px 80px', gap: 12, padding: '10px 20px', borderBottom: '1px solid rgba(255,255,255,.06)', fontSize: '0.72em', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          <span>Severity</span><span>Provider</span><span>Rule / Resource</span><span>File</span><span>Status</span><span></span>
        </div>
        {loading ? <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>Loading…</div> : filtered.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6ee7b7' }}>
            <CheckCircle size={32} style={{ margin: '0 auto 10px' }} /><div>No violations in this category</div>
          </div>
        ) : filtered.map(v => (
          <div key={v.id} style={{ display: 'grid', gridTemplateColumns: '90px 80px 1fr 160px 100px 80px', gap: 12, padding: '12px 20px', borderBottom: '1px solid rgba(255,255,255,.04)', alignItems: 'center', opacity: v.suppressed ? 0.5 : 1 }}>
            <span style={{ fontSize: '0.72em', fontWeight: 700, color: SEV_COLOR[v.severity], background: `${SEV_COLOR[v.severity]}15`, borderRadius: 20, padding: '3px 8px', textAlign: 'center' }}>{v.severity.toUpperCase()}</span>
            <span style={{ fontSize: '0.75em', fontWeight: 700, color: PROVIDER_COLOR[v.provider] || '#94a3b8', textTransform: 'uppercase' }}>{v.provider}</span>
            <div>
              <div style={{ fontSize: '0.82em', fontWeight: 600, marginBottom: 2 }}>{v.rule}</div>
              <div style={{ fontSize: '0.72em', color: '#64748b', fontFamily: 'monospace' }}>{v.resource}</div>
            </div>
            <span style={{ fontSize: '0.72em', color: '#94a3b8', fontFamily: 'monospace' }}>{v.file}:{v.line}</span>
            <span style={{ fontSize: '0.72em', color: v.suppressed ? '#94a3b8' : '#fca5a5' }}>{v.suppressed ? 'Suppressed' : 'Open'}</span>
            {!v.suppressed && (
              <button onClick={() => suppress(v.id)} disabled={suppressing === v.id}
                style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'rgba(255,255,255,.06)', border: '1px solid rgba(255,255,255,.1)', color: '#94a3b8', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: '0.72em' }}>
                <EyeOff size={10} /> {suppressing === v.id ? '…' : 'Suppress'}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default IaCSecurityDashboard;
