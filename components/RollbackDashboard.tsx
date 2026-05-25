import React, { useState, useEffect, useCallback } from 'react';
import { RotateCcw, CheckCircle, Clock, AlertTriangle, RefreshCw, ChevronRight, Archive } from 'lucide-react';

interface Checkpoint {
  id: string;
  agent_id: string;
  agent_hostname: string;
  action: string;
  timestamp: number;
  files: string[];
  services: string[];
  status: 'available' | 'restored' | 'expired';
}

function timeAgo(ts: number) {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

export function RollbackDashboard() {
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [restoring, setRestoring] = useState<string | null>(null);
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);

  const token = sessionStorage.getItem('access_token');
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const fetchCheckpoints = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/rollback/checkpoints', { headers });
      if (res.ok) setCheckpoints(await res.json());
    } catch (_) {}
    setLoading(false);
  }, []);

  useEffect(() => { fetchCheckpoints(); }, [fetchCheckpoints]);

  const restore = useCallback(async (id: string) => {
    setRestoring(id);
    setMessage(null);
    try {
      const res = await fetch(`/api/rollback/checkpoints/${id}/restore`, { method: 'POST', headers });
      const data = await res.json();
      setMessage({ text: res.ok ? 'Rollback initiated successfully' : (data.detail || 'Rollback failed'), ok: res.ok });
      if (res.ok) fetchCheckpoints();
    } catch (_) {
      setMessage({ text: 'Network error', ok: false });
    }
    setRestoring(null);
  }, [fetchCheckpoints]);

  const statusIcon = (s: Checkpoint['status']) => {
    if (s === 'available') return <Clock size={14} color="#6ee7b7" />;
    if (s === 'restored') return <CheckCircle size={14} color="#94a3b8" />;
    return <AlertTriangle size={14} color="#fca5a5" />;
  };

  const statusColor = (s: Checkpoint['status']) => {
    if (s === 'available') return '#6ee7b7';
    if (s === 'restored') return '#94a3b8';
    return '#fca5a5';
  };

  return (
    <div style={{ padding: '28px 32px', color: '#f1f5f9', fontFamily: 'Inter, sans-serif', minHeight: '100vh', background: '#040812' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <div>
          <div style={{ fontSize: '0.72em', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6366f1', marginBottom: 6 }}>AUTOMATION</div>
          <h1 style={{ fontSize: '1.8em', fontWeight: 900, letterSpacing: '-0.03em', margin: 0 }}>Rollback & Checkpoints</h1>
          <p style={{ color: '#94a3b8', fontSize: '0.85em', marginTop: 4 }}>System state checkpoints created before autonomous actions — restore any point</p>
        </div>
        <button onClick={fetchCheckpoints}
          style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(99,102,241,.15)', border: '1px solid rgba(99,102,241,.3)', color: '#a5b4fc', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: '0.82em' }}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {message && (
        <div style={{
          marginBottom: 20, padding: '12px 20px', borderRadius: 10, fontSize: '0.85em', fontWeight: 600,
          background: message.ok ? 'rgba(16,185,129,.1)' : 'rgba(239,68,68,.1)',
          border: `1px solid ${message.ok ? 'rgba(16,185,129,.3)' : 'rgba(239,68,68,.3)'}`,
          color: message.ok ? '#6ee7b7' : '#fca5a5',
        }}>{message.text}</div>
      )}

      {loading ? (
        <div style={{ textAlign: 'center', color: '#94a3b8', padding: 60 }}>Loading checkpoints…</div>
      ) : checkpoints.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: '#94a3b8' }}>
          <Archive size={40} style={{ margin: '0 auto 12px', opacity: 0.4 }} />
          <div style={{ fontWeight: 600 }}>No checkpoints yet</div>
          <div style={{ fontSize: '0.82em', marginTop: 4 }}>Checkpoints are created automatically before autonomous actions run</div>
        </div>
      ) : (
        <div style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 140px 200px 120px 100px', gap: 16, padding: '10px 24px', borderBottom: '1px solid rgba(255,255,255,.06)', fontSize: '0.72em', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            <span>Checkpoint</span>
            <span>Agent</span>
            <span>Files / Services</span>
            <span>Status</span>
            <span></span>
          </div>
          {checkpoints.map(ckpt => (
            <div key={ckpt.id} style={{
              display: 'grid', gridTemplateColumns: '1fr 140px 200px 120px 100px', gap: 16,
              padding: '14px 24px', borderBottom: '1px solid rgba(255,255,255,.04)', alignItems: 'center',
            }}>
              <div>
                <div style={{ fontSize: '0.85em', fontWeight: 600, marginBottom: 2 }}>{ckpt.action}</div>
                <div style={{ fontSize: '0.75em', color: '#64748b', fontFamily: 'monospace' }}>{ckpt.id} · {timeAgo(ckpt.timestamp)}</div>
              </div>
              <div style={{ fontSize: '0.82em', color: '#94a3b8' }}>{ckpt.agent_hostname || ckpt.agent_id}</div>
              <div style={{ fontSize: '0.75em', color: '#94a3b8' }}>
                {ckpt.files.length > 0 && <div>{ckpt.files.length} file{ckpt.files.length !== 1 ? 's' : ''}</div>}
                {ckpt.services.length > 0 && <div>{ckpt.services.length} service{ckpt.services.length !== 1 ? 's' : ''}</div>}
                {ckpt.files.length === 0 && ckpt.services.length === 0 && <div>State only</div>}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.78em', fontWeight: 700, color: statusColor(ckpt.status) }}>
                {statusIcon(ckpt.status)} {ckpt.status}
              </div>
              <div>
                {ckpt.status === 'available' && (
                  <button onClick={() => restore(ckpt.id)} disabled={restoring === ckpt.id}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 5, background: 'rgba(99,102,241,.15)',
                      border: '1px solid rgba(99,102,241,.3)', color: '#a5b4fc', borderRadius: 6,
                      padding: '5px 12px', cursor: restoring === ckpt.id ? 'wait' : 'pointer', fontSize: '0.78em', fontWeight: 600,
                    }}>
                    <RotateCcw size={11} className={restoring === ckpt.id ? 'animate-spin' : ''} />
                    {restoring === ckpt.id ? 'Restoring…' : 'Restore'}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default RollbackDashboard;
