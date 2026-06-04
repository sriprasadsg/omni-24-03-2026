import React, { useState, useEffect, useCallback } from 'react';
import { Key, Monitor, Lock, RotateCcw, RefreshCw, Play, Square, Terminal, Clock } from 'lucide-react';
import { showToast } from '../utils/toast';

type Tab = 'accounts' | 'sessions' | 'vault' | 'audit';

interface PAMAccount {
  id: string;
  name: string;
  type: string;
  target: string;
  checkout_status: 'available' | 'checked_out';
  checked_out_by?: string;
  last_used: number;
  rotation_days: number;
  status: string;
}

interface PAMSession {
  id: string;
  account_id: string;
  target_host: string;
  protocol: string;
  user: string;
  started_at: number;
  status: 'active' | 'ended';
  duration_seconds: number;
  commands_executed: number;
  recording_path: string;
}

interface VaultEntry {
  id: string;
  name: string;
  type: string;
  target: string;
  username: string;
  last_rotated: number;
  rotation_count: number;
  auto_rotate: boolean;
  rotation_interval_days: number;
}

interface CommandLog {
  id: string;
  session_id: string;
  user: string;
  target: string;
  command: string;
  executed_at: number;
  exit_code: number;
  risk: 'low' | 'medium' | 'high' | 'critical';
}

interface PAMStats {
  privileged_accounts: number;
  active_sessions: number;
  vault_entries: number;
  sessions_today: number;
  rotations_last_30d: number;
  risk_score: number;
}

function timeAgo(ts: number) {
  const d = Date.now() / 1000 - ts;
  if (d < 60) return `${Math.round(d)}s ago`;
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
}

function fmt(secs: number) {
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.round(secs / 60)}m`;
  return `${Math.round(secs / 3600)}h ${Math.round((secs % 3600) / 60)}m`;
}

const RISK_COLOR: Record<string, string> = { low: '#6ee7b7', medium: '#fcd34d', high: '#fca5a5', critical: '#f87171' };
const TYPE_ICON: Record<string, string> = { database: '🗄️', cloud: '☁️', kubernetes: '⎈', windows: '🖥️', ssh_key: '🔑', cloud_credential: '☁️', database_credential: '🗄️' };

export function PAMDashboard() {
  const [tab, setTab] = useState<Tab>('accounts');
  const [accounts, setAccounts] = useState<PAMAccount[]>([]);
  const [sessions, setSessions] = useState<PAMSession[]>([]);
  const [vault, setVault] = useState<VaultEntry[]>([]);
  const [audit, setAudit] = useState<CommandLog[]>([]);
  const [stats, setStats] = useState<PAMStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [rotating, setRotating] = useState<string | null>(null);

  const token = sessionStorage.getItem('access_token');
  const headers = token ? { Authorization: `Bearer ${token}` } : {};

  const fetchAll = useCallback(async () => {
    setLoading(true);
    const [a, s, v, au, st] = await Promise.all([
      fetch('/api/pam/accounts', { headers }).then(r => r.ok ? r.json() : []),
      fetch('/api/pam/sessions', { headers }).then(r => r.ok ? r.json() : []),
      fetch('/api/pam/vault', { headers }).then(r => r.ok ? r.json() : []),
      fetch('/api/pam/audit', { headers }).then(r => r.ok ? r.json() : []),
      fetch('/api/pam/stats', { headers }).then(r => r.ok ? r.json() : null),
    ]).catch(() => [[], [], [], [], null]);
    setAccounts(Array.isArray(a) ? a : []);
    setSessions(Array.isArray(s) ? s : []);
    setVault(Array.isArray(v) ? v : []);
    setAudit(Array.isArray(au) ? au : []);
    setStats(st);
    setLoading(false);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const rotateCredential = useCallback(async (id: string) => {
    setRotating(id);
    try {
      const res = await fetch(`/api/pam/vault/${id}/rotate`, { method: 'POST', headers });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? 'Rotation failed');
      setVault(prev => prev.map(e => e.id === id ? { ...e, last_rotated: Date.now() / 1000, rotation_count: e.rotation_count + 1 } : e));
    } catch (e) {
      console.error('PAM credential rotation failed:', e);
      showToast(e instanceof Error ? e.message : 'Failed to rotate credential', 'error');
    } finally {
      setRotating(null);
    }
  }, []);

  const tabs: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: 'accounts', label: 'Privileged Accounts', icon: <Key size={14} /> },
    { key: 'sessions', label: 'Sessions', icon: <Terminal size={14} /> },
    { key: 'vault', label: 'Credential Vault', icon: <Lock size={14} /> },
    { key: 'audit', label: 'Command Audit', icon: <Monitor size={14} /> },
  ];

  return (
    <div style={{ padding: '28px 32px', color: '#f1f5f9', fontFamily: 'Inter, sans-serif', minHeight: '100vh', background: '#040812' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <div>
          <div style={{ fontSize: '0.72em', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6366f1', marginBottom: 6 }}>Identity & Access</div>
          <h1 style={{ fontSize: '1.8em', fontWeight: 900, letterSpacing: '-0.03em', margin: 0 }}>Privileged Access Management</h1>
          <p style={{ color: '#94a3b8', fontSize: '0.85em', marginTop: 4 }}>Credential vault · Session recording · Command audit · Auto-rotation</p>
        </div>
        <button onClick={fetchAll} style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(99,102,241,.15)', border: '1px solid rgba(99,102,241,.3)', color: '#a5b4fc', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: '0.82em' }}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 14, marginBottom: 28 }}>
          {[
            { label: 'Privileged Accounts', value: stats.privileged_accounts, color: '#a5b4fc' },
            { label: 'Active Sessions', value: stats.active_sessions, color: stats.active_sessions > 0 ? '#fcd34d' : '#6ee7b7' },
            { label: 'Vault Entries', value: stats.vault_entries, color: '#a5b4fc' },
            { label: 'Sessions Today', value: stats.sessions_today, color: '#94a3b8' },
            { label: 'Rotations (30d)', value: stats.rotations_last_30d, color: '#6ee7b7' },
            { label: 'Risk Score', value: stats.risk_score, color: stats.risk_score < 30 ? '#6ee7b7' : stats.risk_score < 70 ? '#fcd34d' : '#fca5a5' },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 12, padding: '16px', textAlign: 'center' }}>
              <div style={{ fontSize: '1.8em', fontWeight: 900, color }}>{value}</div>
              <div style={{ fontSize: '0.72em', color: '#94a3b8', marginTop: 4 }}>{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 2, background: 'rgba(255,255,255,.04)', borderRadius: 10, padding: 4, marginBottom: 20, width: 'fit-content' }}>
        {tabs.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} style={{
            display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', borderRadius: 8, border: 'none', cursor: 'pointer', fontSize: '0.82em', fontWeight: 600,
            background: tab === t.key ? 'rgba(99,102,241,.25)' : 'transparent',
            color: tab === t.key ? '#a5b4fc' : '#94a3b8',
          }}>{t.icon} {t.label}</button>
        ))}
      </div>

      {loading ? <div style={{ padding: 60, textAlign: 'center', color: '#94a3b8' }}>Loading…</div> : (
        <div style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, overflow: 'hidden' }}>

          {/* Accounts tab */}
          {tab === 'accounts' && accounts.map(acc => (
            <div key={acc.id} style={{ display: 'grid', gridTemplateColumns: '40px 1fr 120px 140px 80px', gap: 16, padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,.04)', alignItems: 'center' }}>
              <span style={{ fontSize: '1.3em' }}>{TYPE_ICON[acc.type] || '🔑'}</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: '0.88em' }}>{acc.name}</div>
                <div style={{ fontSize: '0.72em', color: '#64748b' }}>{acc.target} · rotate every {acc.rotation_days}d</div>
              </div>
              <span style={{
                fontSize: '0.72em', fontWeight: 700, padding: '3px 10px', borderRadius: 20,
                background: acc.checkout_status === 'available' ? 'rgba(16,185,129,.12)' : 'rgba(245,158,11,.12)',
                color: acc.checkout_status === 'available' ? '#6ee7b7' : '#fcd34d',
              }}>{acc.checkout_status === 'available' ? 'Available' : `Checked out`}</span>
              {acc.checked_out_by && <span style={{ fontSize: '0.72em', color: '#94a3b8' }}>by {acc.checked_out_by}</span>}
              {!acc.checked_out_by && <span style={{ fontSize: '0.72em', color: '#64748b' }}>last used {timeAgo(acc.last_used)}</span>}
              <span style={{ fontSize: '0.72em', color: acc.status === 'active' ? '#6ee7b7' : '#fca5a5', fontWeight: 700 }}>{acc.status}</span>
            </div>
          ))}

          {/* Sessions tab */}
          {tab === 'sessions' && sessions.map(s => (
            <div key={s.id} style={{ display: 'grid', gridTemplateColumns: '100px 1fr 120px 100px 80px', gap: 16, padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,.04)', alignItems: 'center' }}>
              <span style={{
                fontSize: '0.72em', fontWeight: 700, padding: '3px 10px', borderRadius: 20, textAlign: 'center',
                background: s.status === 'active' ? 'rgba(245,158,11,.12)' : 'rgba(16,185,129,.12)',
                color: s.status === 'active' ? '#fcd34d' : '#6ee7b7',
              }}>{s.status}</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: '0.88em' }}>{s.user} → {s.target_host}</div>
                <div style={{ fontSize: '0.72em', color: '#64748b' }}>{s.protocol.toUpperCase()} · started {timeAgo(s.started_at)}</div>
              </div>
              <span style={{ fontSize: '0.78em', color: '#94a3b8' }}>{fmt(s.duration_seconds)}</span>
              <span style={{ fontSize: '0.78em', color: '#94a3b8' }}>{s.commands_executed} cmds</span>
              <a href={s.recording_path} style={{ fontSize: '0.72em', color: '#6366f1', textDecoration: 'none' }}>▶ Replay</a>
            </div>
          ))}

          {/* Vault tab */}
          {tab === 'vault' && vault.map(e => (
            <div key={e.id} style={{ display: 'grid', gridTemplateColumns: '40px 1fr 120px 120px 80px', gap: 16, padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,.04)', alignItems: 'center' }}>
              <span style={{ fontSize: '1.2em' }}>{TYPE_ICON[e.type] || '🔑'}</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: '0.88em' }}>{e.name}</div>
                <div style={{ fontSize: '0.72em', color: '#64748b' }}>{e.target} · {e.username}</div>
              </div>
              <div style={{ fontSize: '0.75em' }}>
                <div style={{ color: '#94a3b8' }}>Last rotated</div>
                <div style={{ color: '#f1f5f9', fontWeight: 600 }}>{timeAgo(e.last_rotated)}</div>
              </div>
              <div style={{ fontSize: '0.75em' }}>
                <div style={{ color: '#94a3b8' }}>Rotations</div>
                <div style={{ color: '#6ee7b7', fontWeight: 600 }}>{e.rotation_count} · {e.rotation_interval_days}d cycle</div>
              </div>
              <button onClick={() => rotateCredential(e.id)} disabled={rotating === e.id}
                style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'rgba(99,102,241,.15)', border: '1px solid rgba(99,102,241,.3)', color: '#a5b4fc', borderRadius: 6, padding: '5px 10px', cursor: 'pointer', fontSize: '0.72em', fontWeight: 600 }}>
                <RotateCcw size={11} /> {rotating === e.id ? '…' : 'Rotate'}
              </button>
            </div>
          ))}

          {/* Audit tab */}
          {tab === 'audit' && audit.map(cmd => (
            <div key={cmd.id} style={{ display: 'grid', gridTemplateColumns: '80px 120px 1fr 80px 60px', gap: 16, padding: '12px 20px', borderBottom: '1px solid rgba(255,255,255,.04)', alignItems: 'center' }}>
              <span style={{ fontSize: '0.72em', fontWeight: 700, color: RISK_COLOR[cmd.risk], background: `${RISK_COLOR[cmd.risk]}15`, borderRadius: 20, padding: '3px 8px', textAlign: 'center' }}>{cmd.risk.toUpperCase()}</span>
              <div>
                <div style={{ fontSize: '0.78em', fontWeight: 600 }}>{cmd.user}</div>
                <div style={{ fontSize: '0.7em', color: '#64748b' }}>{cmd.target}</div>
              </div>
              <code style={{ fontSize: '0.78em', color: '#a5b4fc', background: 'rgba(99,102,241,.08)', padding: '4px 8px', borderRadius: 6, fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{cmd.command}</code>
              <span style={{ fontSize: '0.72em', color: '#64748b' }}>{timeAgo(cmd.executed_at)}</span>
              <span style={{ fontSize: '0.72em', color: cmd.exit_code === 0 ? '#6ee7b7' : '#fca5a5', fontWeight: 700 }}>exit {cmd.exit_code}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default PAMDashboard;
