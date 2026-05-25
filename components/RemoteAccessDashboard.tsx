import React, { useState, useEffect, useCallback } from 'react';
import { Monitor, Terminal, RefreshCw, Wifi, WifiOff, ChevronRight } from 'lucide-react';
import { RemoteDesktop } from './RemoteDesktop';
import { RemoteTerminal } from './RemoteTerminal';
import { Agent } from '../types';

type AccessMode = 'desktop' | 'terminal';

export function RemoteAccessDashboard() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [mode, setMode] = useState<AccessMode>('terminal');

  const token = sessionStorage.getItem('access_token');
  const headers = token ? { Authorization: `Bearer ${token}` } : {};

  const fetchAgents = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/agents', { headers });
      if (res.ok) {
        const data = await res.json();
        setAgents(Array.isArray(data) ? data : data.agents || []);
      }
    } catch (_) {}
    setLoading(false);
  }, []);

  useEffect(() => { fetchAgents(); }, [fetchAgents]);

  const onlineAgents = agents.filter(a => a.status === 'Online');

  if (selectedAgent) {
    if (mode === 'desktop') {
      return (
        <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 24px', background: 'rgba(255,255,255,.04)', borderBottom: '1px solid rgba(255,255,255,.08)' }}>
            <button onClick={() => setSelectedAgent(null)}
              style={{ background: 'rgba(255,255,255,.08)', border: 'none', color: '#94a3b8', borderRadius: 6, padding: '6px 14px', cursor: 'pointer', fontSize: '0.82em' }}>
              ← Back
            </button>
            <Monitor size={16} color="#6366f1" />
            <span style={{ color: '#f1f5f9', fontWeight: 600 }}>Remote Desktop — {selectedAgent.hostname || selectedAgent.id}</span>
          </div>
          <div style={{ flex: 1, overflow: 'hidden' }}>
            <RemoteDesktop agentId={selectedAgent.id} />
          </div>
        </div>
      );
    }
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 24px', background: 'rgba(255,255,255,.04)', borderBottom: '1px solid rgba(255,255,255,.08)' }}>
          <button onClick={() => setSelectedAgent(null)}
            style={{ background: 'rgba(255,255,255,.08)', border: 'none', color: '#94a3b8', borderRadius: 6, padding: '6px 14px', cursor: 'pointer', fontSize: '0.82em' }}>
            ← Back
          </button>
          <Terminal size={16} color="#10b981" />
          <span style={{ color: '#f1f5f9', fontWeight: 600 }}>Remote Terminal — {selectedAgent.hostname || selectedAgent.id}</span>
        </div>
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <RemoteTerminal agent={selectedAgent} onClose={() => setSelectedAgent(null)} />
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: '28px 32px', color: '#f1f5f9', fontFamily: 'Inter, sans-serif', minHeight: '100vh', background: '#040812' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <div>
          <div style={{ fontSize: '0.72em', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6366f1', marginBottom: 6 }}>AGENTS</div>
          <h1 style={{ fontSize: '1.8em', fontWeight: 900, letterSpacing: '-0.03em', margin: 0 }}>Remote Access</h1>
          <p style={{ color: '#94a3b8', fontSize: '0.85em', marginTop: 4 }}>Connect to agents via Remote Desktop or Terminal</p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <div style={{ display: 'flex', background: 'rgba(255,255,255,.06)', borderRadius: 8, padding: 3, gap: 2 }}>
            {(['terminal', 'desktop'] as AccessMode[]).map(m => (
              <button key={m} onClick={() => setMode(m)} style={{
                display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: '0.82em', fontWeight: 600,
                background: mode === m ? 'rgba(99,102,241,.25)' : 'transparent',
                color: mode === m ? '#a5b4fc' : '#94a3b8',
              }}>
                {m === 'terminal' ? <Terminal size={13} /> : <Monitor size={13} />}
                {m === 'terminal' ? 'Terminal' : 'Desktop'}
              </button>
            ))}
          </div>
          <button onClick={fetchAgents} style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(99,102,241,.15)', border: '1px solid rgba(99,102,241,.3)', color: '#a5b4fc', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: '0.82em' }}>
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', color: '#94a3b8', padding: 60 }}>Loading agents…</div>
      ) : onlineAgents.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: '#94a3b8' }}>
          <WifiOff size={40} style={{ margin: '0 auto 12px', opacity: 0.4 }} />
          <div style={{ fontWeight: 600 }}>No online agents</div>
          <div style={{ fontSize: '0.82em', marginTop: 4 }}>Agents must be online to accept remote connections</div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
          {onlineAgents.map(agent => (
            <div key={agent.id} onClick={() => setSelectedAgent(agent)} style={{
              background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, padding: '20px 24px',
              cursor: 'pointer', transition: 'all 0.2s',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = 'rgba(99,102,241,.4)')}
              onMouseLeave={e => (e.currentTarget.style.borderColor = 'rgba(255,255,255,.08)')}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <div style={{ width: 40, height: 40, borderRadius: 10, background: 'rgba(16,185,129,.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Wifi size={18} color="#10b981" />
                </div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: '0.92em' }}>{agent.hostname || agent.id}</div>
                  <div style={{ fontSize: '0.75em', color: '#94a3b8', marginTop: 2 }}>
                    {agent.ipAddress || agent.platform || 'Unknown platform'} · {mode === 'terminal' ? 'Terminal' : 'Desktop'}
                  </div>
                </div>
              </div>
              <ChevronRight size={16} color="#94a3b8" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default RemoteAccessDashboard;
