import React, { useState, useEffect, useCallback } from 'react';
import { Shield, CheckCircle, XCircle, AlertTriangle, RefreshCw, ChevronDown, ChevronRight, Download } from 'lucide-react';

const API = '/api/frameworks';

interface ControlResult {
  id: string;
  title: string;
  description: string;
  status: 'pass' | 'fail' | 'partial' | 'not_applicable';
  evidence: string;
  evaluated_at: string;
  function?: string;
  theme?: string;
  category?: string;
  ig_level?: number;
}

interface FrameworkResult {
  framework_id: string;
  framework_name: string;
  version: string;
  score: number;
  passed: number;
  partial: number;
  failed: number;
  not_applicable: number;
  total: number;
  controls: ControlResult[];
  evaluated_at: string;
}

interface FrameworkSummary {
  [key: string]: {
    name: string;
    score: number;
    passed: number;
    partial: number;
    failed: number;
    not_applicable: number;
    total: number;
  };
}

const FRAMEWORK_IDS = ['nist_csf', 'cis_v8', 'iso27001_2022', 'hipaa', 'pci_dss', 'soc2'];
const FRAMEWORK_COLORS: Record<string, string> = {
  nist_csf: '#6366f1',
  cis_v8: '#10b981',
  iso27001_2022: '#06b6d4',
  hipaa: '#ec4899',
  pci_dss: '#f59e0b',
  soc2: '#8b5cf6',
};

function ScoreRing({ score, color }: { score: number; color: string }) {
  const r = 28;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  return (
    <svg width={70} height={70} viewBox="0 0 70 70">
      <circle cx={35} cy={35} r={r} fill="none" stroke="rgba(255,255,255,.07)" strokeWidth={6} />
      <circle cx={35} cy={35} r={r} fill="none" stroke={color} strokeWidth={6}
        strokeDasharray={circ} strokeDashoffset={offset}
        strokeLinecap="round" transform="rotate(-90 35 35)" style={{ transition: 'stroke-dashoffset 0.8s ease' }} />
      <text x={35} y={39} textAnchor="middle" fill="#f1f5f9" fontSize={13} fontWeight={900}>{score}%</text>
    </svg>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { bg: string; color: string; label: string; icon: React.ReactNode }> = {
    pass: { bg: 'rgba(16,185,129,.12)', color: '#6ee7b7', label: 'Pass', icon: <CheckCircle size={11} /> },
    partial: { bg: 'rgba(245,158,11,.12)', color: '#fcd34d', label: 'Partial', icon: <AlertTriangle size={11} /> },
    fail: { bg: 'rgba(239,68,68,.12)', color: '#fca5a5', label: 'Fail', icon: <XCircle size={11} /> },
    not_applicable: { bg: 'rgba(148,163,184,.1)', color: '#94a3b8', label: 'N/A', icon: null },
  };
  const c = cfg[status] || cfg.not_applicable;
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, background: c.bg, color: c.color, borderRadius: 20, padding: '3px 10px', fontSize: '0.72em', fontWeight: 700 }}>
      {c.icon} {c.label}
    </span>
  );
}

export function ComplianceFrameworksDashboard() {
  const [summary, setSummary] = useState<FrameworkSummary>({});
  const [selected, setSelected] = useState<string>('nist_csf');
  const [detail, setDetail] = useState<FrameworkResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
  const [filterStatus, setFilterStatus] = useState<string>('all');

  const token = localStorage.getItem('access_token');
  const headers = token ? { Authorization: `Bearer ${token}` } : {};

  const fetchSummary = useCallback(async () => {
    try {
      const res = await fetch(`${API}/summary`, { headers });
      if (res.ok) setSummary(await res.json());
    } catch (_) {}
    setLoading(false);
  }, []);

  const fetchDetail = useCallback(async (fid: string) => {
    setDetailLoading(true);
    try {
      const res = await fetch(`${API}/${fid}`, { headers });
      if (res.ok) setDetail(await res.json());
    } catch (_) {}
    setDetailLoading(false);
  }, []);

  useEffect(() => { fetchSummary(); }, [fetchSummary]);
  useEffect(() => { fetchDetail(selected); }, [selected, fetchDetail]);

  const grouped = detail ? detail.controls.reduce((acc, ctrl) => {
    const group = ctrl.function || ctrl.theme || 'General';
    if (!acc[group]) acc[group] = [];
    acc[group].push(ctrl);
    return acc;
  }, {} as Record<string, ControlResult[]>) : {};

  const toggleGroup = (g: string) => setExpandedGroups(p => ({ ...p, [g]: !p[g] }));

  const filteredControls = (ctrls: ControlResult[]) =>
    filterStatus === 'all' ? ctrls : ctrls.filter(c => c.status === filterStatus);

  return (
    <div style={{ padding: '28px 32px', color: '#f1f5f9', fontFamily: 'Inter, sans-serif', minHeight: '100vh', background: '#040812' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <div>
          <div style={{ fontSize: '0.72em', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6366f1', marginBottom: 6 }}>GRC</div>
          <h1 style={{ fontSize: '1.8em', fontWeight: 900, letterSpacing: '-0.03em', margin: 0 }}>Compliance Frameworks</h1>
          <p style={{ color: '#94a3b8', fontSize: '0.85em', marginTop: 4 }}>Automated control evaluation — NIST CSF · CIS v8 · ISO 27001 · HIPAA · PCI-DSS · SOC 2</p>
        </div>
        <button onClick={() => { fetchSummary(); fetchDetail(selected); }}
          style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(99,102,241,.15)', border: '1px solid rgba(99,102,241,.3)', color: '#a5b4fc', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: '0.82em' }}>
          <RefreshCw size={13} /> Re-evaluate
        </button>
      </div>

      {/* Framework score cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 28 }}>
        {FRAMEWORK_IDS.map(fid => {
          const s = summary[fid];
          const color = FRAMEWORK_COLORS[fid] || '#6366f1';
          const isSelected = selected === fid;
          return (
            <div key={fid} onClick={() => setSelected(fid)} style={{
              background: isSelected ? `${color}18` : 'rgba(255,255,255,.04)',
              border: `1px solid ${isSelected ? color + '60' : 'rgba(255,255,255,.08)'}`,
              borderRadius: 14, padding: '20px 24px', cursor: 'pointer', transition: 'all 0.2s',
              display: 'flex', alignItems: 'center', gap: 20,
            }}>
              {s ? <ScoreRing score={Math.round(s.score)} color={color} /> : <div style={{ width: 70, height: 70, background: 'rgba(255,255,255,.05)', borderRadius: '50%' }} />}
              <div>
                <div style={{ fontWeight: 800, fontSize: '0.95em', marginBottom: 4 }}>{s?.name || fid}</div>
                {s && (
                  <div style={{ display: 'flex', gap: 10, fontSize: '0.78em' }}>
                    <span style={{ color: '#6ee7b7' }}>✓ {s.passed}</span>
                    <span style={{ color: '#fcd34d' }}>~ {s.partial}</span>
                    <span style={{ color: '#fca5a5' }}>✗ {s.failed}</span>
                  </div>
                )}
                {loading && <span style={{ color: '#94a3b8', fontSize: '0.78em' }}>Evaluating…</span>}
              </div>
            </div>
          );
        })}
      </div>

      {/* Detail panel */}
      {detailLoading ? (
        <div style={{ textAlign: 'center', color: '#94a3b8', padding: 60 }}>Running control checks…</div>
      ) : detail && (
        <div style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, overflow: 'hidden' }}>
          {/* Panel header */}
          <div style={{ padding: '16px 24px', borderBottom: '1px solid rgba(255,255,255,.07)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <Shield size={16} color={FRAMEWORK_COLORS[selected]} />
              <span style={{ fontWeight: 700 }}>{detail.framework_name} v{detail.version}</span>
              <span style={{ fontSize: '0.78em', color: '#94a3b8' }}>{detail.total} controls · evaluated {new Date(detail.evaluated_at).toLocaleTimeString()}</span>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              {['all', 'fail', 'partial', 'pass'].map(f => (
                <button key={f} onClick={() => setFilterStatus(f)} style={{
                  background: filterStatus === f ? 'rgba(99,102,241,.2)' : 'transparent',
                  border: '1px solid rgba(255,255,255,.1)', color: filterStatus === f ? '#a5b4fc' : '#94a3b8',
                  borderRadius: 6, padding: '4px 12px', cursor: 'pointer', fontSize: '0.78em', fontWeight: 600, textTransform: 'capitalize',
                }}>{f === 'all' ? `All (${detail.total})` : f === 'fail' ? `Fail (${detail.failed})` : f === 'partial' ? `Partial (${detail.partial})` : `Pass (${detail.passed})`}</button>
              ))}
            </div>
          </div>

          {/* Grouped controls */}
          <div style={{ maxHeight: 520, overflowY: 'auto' }}>
            {Object.entries(grouped).map(([group, ctrls]) => {
              const filtered = filteredControls(ctrls);
              if (filtered.length === 0) return null;
              const isOpen = expandedGroups[group] !== false;
              const gFails = filtered.filter(c => c.status === 'fail').length;
              return (
                <div key={group}>
                  <div onClick={() => toggleGroup(group)} style={{
                    display: 'flex', alignItems: 'center', gap: 10, padding: '12px 24px',
                    background: 'rgba(255,255,255,.02)', borderBottom: '1px solid rgba(255,255,255,.05)',
                    cursor: 'pointer', userSelect: 'none',
                  }}>
                    {isOpen ? <ChevronDown size={14} color="#94a3b8" /> : <ChevronRight size={14} color="#94a3b8" />}
                    <span style={{ fontWeight: 700, fontSize: '0.88em' }}>{group}</span>
                    <span style={{ fontSize: '0.75em', color: '#94a3b8' }}>{filtered.length} controls</span>
                    {gFails > 0 && <span style={{ marginLeft: 'auto', fontSize: '0.75em', color: '#fca5a5', background: 'rgba(239,68,68,.1)', borderRadius: 20, padding: '2px 10px' }}>{gFails} failing</span>}
                  </div>
                  {isOpen && filtered.map(ctrl => (
                    <div key={ctrl.id} style={{
                      display: 'grid', gridTemplateColumns: '90px 1fr 1fr auto',
                      gap: 16, padding: '12px 24px 12px 48px',
                      borderBottom: '1px solid rgba(255,255,255,.04)',
                      alignItems: 'start',
                    }}>
                      <span style={{ fontSize: '0.78em', fontWeight: 700, color: '#94a3b8', fontFamily: 'monospace' }}>{ctrl.id}</span>
                      <div>
                        <div style={{ fontSize: '0.85em', fontWeight: 600, marginBottom: 2 }}>{ctrl.title}</div>
                        <div style={{ fontSize: '0.75em', color: '#94a3b8', lineHeight: 1.4 }}>{ctrl.description}</div>
                      </div>
                      <span style={{ fontSize: '0.78em', color: '#94a3b8', paddingTop: 2 }}>{ctrl.evidence}</span>
                      <StatusBadge status={ctrl.status} />
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default ComplianceFrameworksDashboard;
