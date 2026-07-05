import React, { useState, useEffect, useCallback } from 'react';
import { Shield, CheckCircle, XCircle, AlertTriangle, RefreshCw, ChevronDown, ChevronRight, Download, Search } from 'lucide-react';
import { authFetch } from '../services/apiService';
import { useUser } from '../contexts/UserContext';

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

const FRAMEWORK_COLOR_PALETTE = [
  '#6366f1', '#10b981', '#06b6d4', '#ec4899', '#f59e0b', '#8b5cf6',
  '#ef4444', '#14b8a6', '#f97316', '#84cc16', '#3b82f6', '#a855f7',
];

function colorForFramework(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  return FRAMEWORK_COLOR_PALETTE[hash % FRAMEWORK_COLOR_PALETTE.length];
}

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
  const { currentUser } = useUser();
  const canTriggerScan = currentUser?.role === 'Super Admin' || currentUser?.role === 'Tenant Admin';

  const [summary, setSummary] = useState<FrameworkSummary>({});
  const [selected, setSelected] = useState<string>('');
  const [detail, setDetail] = useState<FrameworkResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [isScanning, setIsScanning] = useState(false);
  const [scanMessage, setScanMessage] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  const fetchSummary = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await authFetch(`${API}/summary`, { signal });
      if (res.ok) {
        setSummary(await res.json());
        setSummaryError(null);
      } else {
        setSummaryError(`Failed to load frameworks (HTTP ${res.status}).`);
      }
    } catch (e) {
      if ((e as any)?.name !== 'AbortError') {
        console.error('Failed to load compliance summary:', e);
        setSummaryError('Failed to load frameworks. Check backend connection.');
      }
    }
    setLoading(false);
  }, []);

  const fetchDetail = useCallback(async (fid: string, signal?: AbortSignal) => {
    if (!fid) return;
    setDetailLoading(true);
    try {
      const res = await authFetch(`${API}/${fid}`, { signal });
      if (res.ok) {
        setDetail(await res.json());
        setDetailError(null);
      } else {
        setDetailError(`Failed to load control detail (HTTP ${res.status}).`);
      }
    } catch (e) {
      if ((e as any)?.name !== 'AbortError') {
        console.error('Failed to load compliance detail:', e);
        setDetailError('Failed to load control detail. Check backend connection.');
      }
    }
    setDetailLoading(false);
  }, []);

  const triggerScan = useCallback(async () => {
    setIsScanning(true);
    setScanMessage(null);
    try {
      const res = await authFetch(`/api/compliance/${selected}/scan`, { method: 'POST' });
      const data = res.ok ? await res.json() : null;
      const count = data?.agent_count ?? 0;
      setScanMessage(`Scan dispatched to ${count} agent${count !== 1 ? 's' : ''}. Results update in ~60s.`);
      setTimeout(() => {
        fetchSummary();
        fetchDetail(selected);
        setScanMessage(null);
      }, 12000);
    } catch {
      setScanMessage('Failed to dispatch scan. Check backend connection.');
    } finally {
      setIsScanning(false);
    }
  }, [selected, fetchSummary, fetchDetail]);

  const frameworkIds = Object.keys(summary).sort();
  const query = search.trim().toLowerCase();
  const visibleFrameworkIds = query
    ? frameworkIds.filter(fid => fid.toLowerCase().includes(query) || (summary[fid]?.name || '').toLowerCase().includes(query))
    : frameworkIds;

  useEffect(() => {
    const controller = new AbortController();
    fetchSummary(controller.signal);
    return () => controller.abort();
  }, [fetchSummary]);
  useEffect(() => {
    if (!selected && frameworkIds.length > 0) setSelected(frameworkIds[0]);
  }, [frameworkIds, selected]);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    fetchDetail(selected, controller.signal);
    return () => controller.abort();
  }, [selected, fetchDetail]);

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
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <div>
          <div style={{ fontSize: '0.72em', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6366f1', marginBottom: 6 }}>GRC</div>
          <h1 style={{ fontSize: '1.8em', fontWeight: 900, letterSpacing: '-0.03em', margin: 0 }}>Compliance Frameworks</h1>
          <p style={{ color: '#94a3b8', fontSize: '0.85em', marginTop: 4 }}>Automated control evaluation across {frameworkIds.length || ''} configured compliance framework{frameworkIds.length === 1 ? '' : 's'}</p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
          {canTriggerScan ? (
            <button
              onClick={triggerScan}
              disabled={isScanning}
              style={{ display: 'flex', alignItems: 'center', gap: 6, background: isScanning ? 'rgba(99,102,241,.08)' : 'rgba(99,102,241,.15)', border: '1px solid rgba(99,102,241,.3)', color: '#a5b4fc', borderRadius: 8, padding: '8px 16px', cursor: isScanning ? 'not-allowed' : 'pointer', fontSize: '0.82em', opacity: isScanning ? 0.7 : 1 }}>
              <RefreshCw size={13} style={{ animation: isScanning ? 'spin 1s linear infinite' : 'none' }} />
              {isScanning ? 'Dispatching…' : 'Scan All Agents'}
            </button>
          ) : (
            <button
              onClick={() => { fetchSummary(); fetchDetail(selected); }}
              style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(99,102,241,.15)', border: '1px solid rgba(99,102,241,.3)', color: '#a5b4fc', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: '0.82em' }}>
              <RefreshCw size={13} /> Re-evaluate
            </button>
          )}
          {scanMessage && (
            <span style={{ fontSize: '0.75em', color: scanMessage.startsWith('Failed') ? '#fca5a5' : '#6ee7b7' }}>
              {scanMessage}
            </span>
          )}
        </div>
      </div>

      {/* Summary error banner */}
      {summaryError && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
          background: 'rgba(239,68,68,.1)', border: '1px solid rgba(239,68,68,.3)', color: '#fca5a5',
          borderRadius: 8, padding: '10px 16px', marginBottom: 16, fontSize: '0.85em',
        }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><AlertTriangle size={14} /> {summaryError}</span>
          <button onClick={() => fetchSummary()} style={{
            background: 'rgba(239,68,68,.15)', border: '1px solid rgba(239,68,68,.35)', color: '#fca5a5',
            borderRadius: 6, padding: '4px 12px', cursor: 'pointer', fontSize: '0.9em', fontWeight: 600,
          }}>Retry</button>
        </div>
      )}

      {/* Framework search */}
      {frameworkIds.length > 0 && (
        <div style={{ position: 'relative', marginBottom: 16, maxWidth: 360 }}>
          <Search size={14} color="#94a3b8" style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }} />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={`Search ${frameworkIds.length} frameworks…`}
            style={{
              width: '100%', background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)',
              borderRadius: 8, padding: '8px 12px 8px 34px', color: '#f1f5f9', fontSize: '0.85em',
              boxSizing: 'border-box', outline: 'none',
            }}
          />
        </div>
      )}

      {/* Framework score cards */}
      {loading && frameworkIds.length === 0 && (
        <div style={{ textAlign: 'center', color: '#94a3b8', padding: 60 }}>Loading frameworks…</div>
      )}
      {!loading && frameworkIds.length > 0 && visibleFrameworkIds.length === 0 && (
        <div style={{ textAlign: 'center', color: '#94a3b8', padding: 40 }}>No frameworks match "{search}".</div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16, marginBottom: 28 }}>
        {visibleFrameworkIds.map(fid => {
          const s = summary[fid];
          const color = colorForFramework(fid);
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
      {detailError && !detailLoading && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
          background: 'rgba(239,68,68,.1)', border: '1px solid rgba(239,68,68,.3)', color: '#fca5a5',
          borderRadius: 8, padding: '10px 16px', marginBottom: 16, fontSize: '0.85em',
        }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><AlertTriangle size={14} /> {detailError}</span>
          <button onClick={() => fetchDetail(selected)} style={{
            background: 'rgba(239,68,68,.15)', border: '1px solid rgba(239,68,68,.35)', color: '#fca5a5',
            borderRadius: 6, padding: '4px 12px', cursor: 'pointer', fontSize: '0.9em', fontWeight: 600,
          }}>Retry</button>
        </div>
      )}
      {detailLoading ? (
        <div style={{ textAlign: 'center', color: '#94a3b8', padding: 60 }}>Running control checks…</div>
      ) : detail && (
        <div style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, overflow: 'hidden' }}>
          {/* Panel header */}
          <div style={{ padding: '16px 24px', borderBottom: '1px solid rgba(255,255,255,.07)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <Shield size={16} color={colorForFramework(selected)} />
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
