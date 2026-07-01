import React, { useState, useCallback, useEffect } from 'react';
import { Zap, Play, RotateCcw, ChevronDown, History, CheckCircle, XCircle, Clock, RefreshCw } from 'lucide-react';
import { AutonomousRiskRemediation } from './AutonomousRiskRemediation';
import { AgenticStep, AiSystem, AiRisk } from '../types';
import { authFetch, API_BASE } from '../services/apiService';

interface RunState {
  status: 'idle' | 'running' | 'completed' | 'failed';
  steps: AgenticStep[];
  targetSystem: AiSystem | null;
  targetRisk: AiRisk | null;
}

interface AgenticDecision {
  id: string;
  agent_id: string;
  recommended_action: string;
  confidence: number;
  reasoning: string;
  status: string;
  requires_approval: boolean;
  created_at: string;
  reviewed_by?: string;
  reviewed_at?: string;
  reviewer_note?: string;
}

interface SystemOption { id: string; name: string; type: string }
interface RiskOption { id: string; title: string; severity: 'critical' | 'high' | 'medium' | 'Critical' | 'High' | 'Medium' | 'Low' }

const STATUS_STYLES: Record<string, { color: string; icon: React.ReactNode }> = {
  pending_approval: { color: '#fbbf24', icon: <Clock size={13} /> },
  auto_approved:    { color: '#34d399', icon: <CheckCircle size={13} /> },
  approved:         { color: '#34d399', icon: <CheckCircle size={13} /> },
  rejected:         { color: '#f87171', icon: <XCircle size={13} /> },
};

function DecisionHistory() {
  const [decisions, setDecisions] = useState<AgenticDecision[]>([]);
  const [loading, setLoading] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await authFetch('/api/agents/agentic-decisions/all?limit=50');
      if (res.ok) {
        const data = await res.json();
        setDecisions(data.decisions || []);
        setPendingCount(data.pending || 0);
      }
    } catch (e) {
      console.error('Failed to load agentic decisions', e);
    } finally {
      setLoading(false);
    }
  }, []);

  const approve = useCallback(async (decision: AgenticDecision, approved: boolean) => {
    try {
      await authFetch(`/api/agents/${decision.agent_id}/agentic-decisions/${decision.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ approved }),
      });
      load();
    } catch (e) {
      console.error('Approval failed', e);
    }
  }, [load]);

  useEffect(() => { load(); }, [load]);

  const s = { color: '#f1f5f9', fontFamily: 'Inter, sans-serif' };

  return (
    <div style={{ ...s, padding: '28px 32px', minHeight: '100vh', background: '#040812' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: '0.72em', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6366f1', marginBottom: 6 }}>AI ENGINE</div>
          <h1 style={{ fontSize: '1.8em', fontWeight: 900, letterSpacing: '-0.03em', margin: 0 }}>Decision History</h1>
          <p style={{ color: '#94a3b8', fontSize: '0.85em', marginTop: 4 }}>
            Agentic decisions requiring operator review
            {pendingCount > 0 && <span style={{ marginLeft: 10, background: '#fbbf24', color: '#000', borderRadius: 8, padding: '2px 8px', fontSize: '0.78em', fontWeight: 700 }}>{pendingCount} PENDING</span>}
          </p>
        </div>
        <button onClick={load} style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(255,255,255,.08)', border: '1px solid rgba(255,255,255,.12)', color: '#94a3b8', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: '0.82em' }}>
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {decisions.length === 0 ? (
        <div style={{ textAlign: 'center', color: '#475569', padding: '80px 0', border: '1px dashed rgba(255,255,255,.1)', borderRadius: 14 }}>
          No agentic decisions recorded yet. Decisions appear here when agents encounter low-confidence situations requiring operator approval.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {decisions.map(d => {
            const ss = STATUS_STYLES[d.status] || { color: '#94a3b8', icon: null };
            const isPending = d.status === 'pending_approval';
            return (
              <div key={d.id} style={{ background: 'rgba(255,255,255,.04)', border: isPending ? '1px solid rgba(251,191,36,.3)' : '1px solid rgba(255,255,255,.08)', borderRadius: 12, padding: '16px 20px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.78em', fontWeight: 700, color: ss.color }}>
                        {ss.icon} {d.status.replace(/_/g, ' ').toUpperCase()}
                      </span>
                      <span style={{ fontSize: '0.72em', color: '#475569' }}>Agent: {d.agent_id}</span>
                      <span style={{ fontSize: '0.72em', color: '#475569' }}>{new Date(d.created_at).toLocaleString()}</span>
                    </div>
                    <div style={{ fontWeight: 700, marginBottom: 4 }}>{d.recommended_action}</div>
                    <div style={{ fontSize: '0.82em', color: '#94a3b8' }}>{d.reasoning}</div>
                    {d.reviewer_note && <div style={{ fontSize: '0.78em', color: '#6366f1', marginTop: 4 }}>Note: {d.reviewer_note}</div>}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
                    <span style={{ fontSize: '0.75em', color: '#94a3b8' }}>Confidence: {Math.round(d.confidence * 100)}%</span>
                    {isPending && (
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button onClick={() => approve(d, true)} style={{ background: 'rgba(52,211,153,.15)', border: '1px solid rgba(52,211,153,.3)', color: '#34d399', borderRadius: 6, padding: '5px 12px', cursor: 'pointer', fontSize: '0.78em', fontWeight: 700 }}>Approve</button>
                        <button onClick={() => approve(d, false)} style={{ background: 'rgba(248,113,113,.12)', border: '1px solid rgba(248,113,113,.3)', color: '#f87171', borderRadius: 6, padding: '5px 12px', cursor: 'pointer', fontSize: '0.78em', fontWeight: 700 }}>Reject</button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function AIRemediationDashboard() {
  const [activeTab, setActiveTab] = useState<'remediate' | 'history'>('remediate');
  const [systems, setSystems] = useState<SystemOption[]>([]);
  const [risks, setRisks] = useState<RiskOption[]>([]);
  const [selectedSystemId, setSelectedSystemId] = useState('');
  const [selectedRiskId, setSelectedRiskId] = useState('');
  const [loadingSystems, setLoadingSystems] = useState(true);
  const [loadingRisks, setLoadingRisks] = useState(false);
  const [runState, setRunState] = useState<RunState>({
    status: 'idle',
    steps: [],
    targetSystem: null,
    targetRisk: null,
  });
  const [remediationError, setRemediationError] = useState<string | null>(null);

  useEffect(() => {
    setLoadingSystems(true);
    authFetch(`${API_BASE}/ai-systems`)
      .then(r => r.ok ? r.json() : [])
      .then((data: any[]) => {
        const arr = Array.isArray(data) ? data : [];
        const opts = arr.map(s => ({ id: s.id, name: s.name || s.id, type: s.type || s.status || 'system' }));
        setSystems(opts);
        if (opts.length > 0) setSelectedSystemId(opts[0].id);
      })
      .catch(() => setSystems([]))
      .finally(() => setLoadingSystems(false));
  }, []);

  useEffect(() => {
    if (!selectedSystemId) return;
    setLoadingRisks(true);
    setRisks([]);
    authFetch(`${API_BASE}/ai-systems/${selectedSystemId}/risks`)
      .then(r => r.ok ? r.json() : [])
      .then((data: any[]) => {
        const arr = Array.isArray(data) ? data : [];
        const opts = arr.map(r => ({ id: r.id, title: r.title || r.name || 'Unnamed Risk', severity: (r.severity || 'medium').toLowerCase() as RiskOption['severity'] }));
        setRisks(opts);
        if (opts.length > 0) setSelectedRiskId(opts[0].id);
      })
      .catch(() => setRisks([]))
      .finally(() => setLoadingRisks(false));
  }, [selectedSystemId]);

  const selectedSystem = systems.find(s => s.id === selectedSystemId);
  const selectedRisk = risks.find(r => r.id === selectedRiskId);

  const startRemediation = useCallback(async () => {
    if (!selectedSystem || !selectedRisk) return;

    setRunState({
      status: 'running',
      steps: [],
      targetSystem: { id: selectedSystem.id, name: selectedSystem.name, type: selectedSystem.type } as unknown as AiSystem,
      targetRisk: { id: selectedRisk.id, title: selectedRisk.title, severity: selectedRisk.severity } as unknown as AiRisk,
    });

    setRemediationError(null);
    try {
      const res = await authFetch(`${API_BASE}/ai-remediation/run`, {
        method: 'POST',
        body: JSON.stringify({ system_id: selectedSystem.id, risk_id: selectedRisk.id }),
      });
      if (res.status === 403) {
        setRemediationError('Tenant context required. Please re-authenticate.');
        setRunState({ status: 'idle', steps: [], targetSystem: null, targetRisk: null });
        return;
      }
      const data = res.ok ? await res.json() : {};
      const steps: AgenticStep[] = (data.steps || []).map((s: any) => ({
        type: s.type || 'action',
        content: s.content || s.message || '',
        timestamp: s.timestamp || new Date().toISOString(),
      }));
      setRunState(prev => ({ ...prev, status: 'completed', steps }));
    } catch (e) {
      setRunState(prev => ({ ...prev, status: 'failed' }));
    }
  }, [selectedSystem, selectedRisk]);

  const reset = useCallback(() => {
    setRunState({ status: 'idle', steps: [], targetSystem: null, targetRisk: null });
  }, []);

  if (runState.status !== 'idle') {
    return (
      <div style={{ padding: '28px 32px', color: '#f1f5f9', fontFamily: 'Inter, sans-serif', minHeight: '100vh', background: '#040812' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <div>
            <div style={{ fontSize: '0.72em', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6366f1', marginBottom: 6 }}>AI ENGINE</div>
            <h1 style={{ fontSize: '1.8em', fontWeight: 900, letterSpacing: '-0.03em', margin: 0 }}>Autonomous Remediation</h1>
          </div>
          <button onClick={reset} style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(255,255,255,.08)', border: '1px solid rgba(255,255,255,.12)', color: '#94a3b8', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: '0.82em' }}>
            <RotateCcw size={13} /> New Run
          </button>
        </div>
        <AutonomousRiskRemediation runState={runState} onClose={reset} />
      </div>
    );
  }

  const tabStyle = (tab: string) => ({
    padding: '8px 20px',
    borderRadius: 8,
    border: 'none',
    cursor: 'pointer',
    fontSize: '0.85em',
    fontWeight: 700,
    background: activeTab === tab ? 'rgba(99,102,241,.2)' : 'transparent',
    color: activeTab === tab ? '#818cf8' : '#475569',
    display: 'flex' as const,
    alignItems: 'center' as const,
    gap: 6,
  });

  return (
    <div style={{ padding: '28px 32px', color: '#f1f5f9', fontFamily: 'Inter, sans-serif', minHeight: '100vh', background: '#040812' }}>
      {/* Header + Tabs */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontSize: '0.72em', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6366f1', marginBottom: 6 }}>AI ENGINE</div>
        <h1 style={{ fontSize: '1.8em', fontWeight: 900, letterSpacing: '-0.03em', margin: 0 }}>Autonomous Remediation</h1>
      </div>
      <div style={{ display: 'flex', gap: 4, marginBottom: 28, borderBottom: '1px solid rgba(255,255,255,.08)', paddingBottom: 4 }}>
        <button style={tabStyle('remediate')} onClick={() => setActiveTab('remediate')}>
          <Zap size={13} /> Remediate
        </button>
        <button style={tabStyle('history')} onClick={() => setActiveTab('history')}>
          <History size={13} /> Decision History
        </button>
      </div>

      {activeTab === 'history' ? (
        <DecisionHistory />
      ) : (
        <>
          {remediationError && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'rgba(248,113,113,.1)', border: '1px solid rgba(248,113,113,.3)', borderRadius: 10, padding: '12px 16px', marginBottom: 20, fontSize: '0.85em', color: '#f87171' }}>
              <span style={{ fontWeight: 700 }}>⚠</span> {remediationError}
              <button onClick={() => setRemediationError(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#f87171', cursor: 'pointer', opacity: 0.6, fontSize: '1em' }}>✕</button>
            </div>
          )}
          <p style={{ color: '#94a3b8', fontSize: '0.85em', marginBottom: 24 }}>Select a system and risk, then let the AI engine remediate autonomously with full auditability</p>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, maxWidth: 800, marginBottom: 32 }}>
            <div style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, padding: '20px 24px' }}>
              <div style={{ fontSize: '0.75em', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>Target System</div>
              <div style={{ position: 'relative' }}>
                <select value={selectedSystemId} onChange={e => setSelectedSystemId(e.target.value)}
                  style={{ width: '100%', background: 'rgba(255,255,255,.06)', border: '1px solid rgba(255,255,255,.12)', color: '#f1f5f9', borderRadius: 8, padding: '10px 36px 10px 12px', appearance: 'none', fontSize: '0.88em', cursor: 'pointer' }}>
                  {loadingSystems && <option value="">Loading systems…</option>}
                  {!loadingSystems && systems.length === 0 && <option value="">No AI systems found</option>}
                  {systems.map(s => <option key={s.id} value={s.id} style={{ background: '#1e293b' }}>{s.name}</option>)}
                </select>
                <ChevronDown size={14} color="#94a3b8" style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
              </div>
            </div>

            <div style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, padding: '20px 24px' }}>
              <div style={{ fontSize: '0.75em', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>Target Risk</div>
              <div style={{ position: 'relative' }}>
                <select value={selectedRiskId} onChange={e => setSelectedRiskId(e.target.value)}
                  style={{ width: '100%', background: 'rgba(255,255,255,.06)', border: '1px solid rgba(255,255,255,.12)', color: '#f1f5f9', borderRadius: 8, padding: '10px 36px 10px 12px', appearance: 'none', fontSize: '0.88em', cursor: 'pointer' }}>
                  {loadingRisks && <option value="">Loading risks…</option>}
                  {!loadingRisks && risks.length === 0 && <option value="">No risks found for this system</option>}
                  {risks.map(r => <option key={r.id} value={r.id} style={{ background: '#1e293b' }}>{r.title}</option>)}
                </select>
                <ChevronDown size={14} color="#94a3b8" style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
              </div>
            </div>
          </div>

          <div style={{ maxWidth: 800, background: 'rgba(99,102,241,.06)', border: '1px solid rgba(99,102,241,.2)', borderRadius: 14, padding: '20px 24px', marginBottom: 28 }}>
            <div style={{ fontSize: '0.82em', color: '#94a3b8', marginBottom: 12 }}>Remediation Summary</div>
            <div style={{ display: 'flex', gap: 32 }}>
              <div>
                <div style={{ fontSize: '0.72em', color: '#6366f1', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>System</div>
                <div style={{ fontWeight: 700, marginTop: 2 }}>{selectedSystem?.name || '—'}</div>
              </div>
              <div>
                <div style={{ fontSize: '0.72em', color: '#6366f1', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Risk</div>
                <div style={{ fontWeight: 700, marginTop: 2 }}>{selectedRisk?.title || '—'}</div>
              </div>
              <div>
                <div style={{ fontSize: '0.72em', color: '#6366f1', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Severity</div>
                <div style={{ fontWeight: 700, marginTop: 2, color: selectedRisk?.severity === 'critical' || selectedRisk?.severity === 'Critical' ? '#fca5a5' : selectedRisk?.severity === 'high' || selectedRisk?.severity === 'High' ? '#fcd34d' : '#6ee7b7' }}>
                  {selectedRisk ? selectedRisk.severity.toUpperCase() : '—'}
                </div>
              </div>
            </div>
          </div>

          <button onClick={startRemediation} disabled={!selectedSystem || !selectedRisk} style={{
            display: 'flex', alignItems: 'center', gap: 10, background: selectedSystem && selectedRisk ? 'linear-gradient(135deg, #6366f1, #8b5cf6)' : 'rgba(99,102,241,.3)', border: 'none', color: '#fff', borderRadius: 10,
            padding: '14px 28px', cursor: selectedSystem && selectedRisk ? 'pointer' : 'not-allowed', fontSize: '0.95em', fontWeight: 700, boxShadow: selectedSystem && selectedRisk ? '0 0 20px rgba(99,102,241,.4)' : 'none',
          }}>
            <Zap size={16} />
            Start Autonomous Remediation
            <Play size={14} />
          </button>
        </>
      )}
    </div>
  );
}

export default AIRemediationDashboard;
