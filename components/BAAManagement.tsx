import React, { useState, useEffect, useCallback } from 'react';
import { FileText, Plus, CheckCircle, XCircle, Clock, RefreshCw, Shield } from 'lucide-react';

interface BAA {
  id: string;
  business_associate: string;
  contact_email: string;
  services: string[];
  phi_types: string[];
  effective_date: number;
  expiration_date: number;
  status: 'draft' | 'pending_signature' | 'active' | 'expired' | 'terminated';
  signed_at?: number;
  terminated_at?: string;
  termination_reason?: string;
}

interface BAAStats {
  total: number;
  active: number;
  expiring_soon: number;
  expired: number;
  draft: number;
}

function formatDate(ts: number) {
  return new Date(ts * 1000).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

function timeAgo(ts: number) {
  const d = Date.now() / 1000 - ts;
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
}

const STATUS_CFG: Record<string, { bg: string; color: string; label: string }> = {
  active: { bg: 'rgba(16,185,129,.12)', color: '#6ee7b7', label: 'Active' },
  draft: { bg: 'rgba(148,163,184,.1)', color: '#94a3b8', label: 'Draft' },
  pending_signature: { bg: 'rgba(245,158,11,.12)', color: '#fcd34d', label: 'Pending Signature' },
  expired: { bg: 'rgba(239,68,68,.12)', color: '#fca5a5', label: 'Expired' },
  terminated: { bg: 'rgba(239,68,68,.08)', color: '#f87171', label: 'Terminated' },
};

export function BAAManagement() {
  const [baas, setBaas] = useState<BAA[]>([]);
  const [stats, setStats] = useState<BAAStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<string | null>(null);
  const [filter, setFilter] = useState('all');
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ business_associate: '', contact_email: '', services: '', phi_types: '' });

  const token = localStorage.getItem('access_token');
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const fetchAll = useCallback(async () => {
    setLoading(true);
    const [b, s] = await Promise.all([
      fetch('/api/baa', { headers }).then(r => r.ok ? r.json() : []),
      fetch('/api/baa/stats', { headers }).then(r => r.ok ? r.json() : null),
    ]).catch(() => [[], null]);
    setBaas(Array.isArray(b) ? b : []);
    setStats(s);
    setLoading(false);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const sign = useCallback(async (id: string) => {
    setActing(id);
    await fetch(`/api/baa/${id}/sign`, { method: 'POST', headers }).catch(() => {});
    setBaas(prev => prev.map(b => b.id === id ? { ...b, status: 'active' as const, signed_at: Date.now() / 1000 } : b));
    setActing(null);
  }, []);

  const terminate = useCallback(async (id: string) => {
    setActing(id);
    await fetch(`/api/baa/${id}/terminate`, {
      method: 'POST', headers, body: JSON.stringify({ reason: 'Terminated by administrator' }),
    }).catch(() => {});
    setBaas(prev => prev.map(b => b.id === id ? { ...b, status: 'terminated' as const } : b));
    setActing(null);
  }, []);

  const createBAA = useCallback(async () => {
    if (!form.business_associate) return;
    const payload = {
      business_associate: form.business_associate,
      contact_email: form.contact_email,
      services: form.services.split(',').map(s => s.trim()).filter(Boolean),
      phi_types: form.phi_types.split(',').map(s => s.trim()).filter(Boolean),
    };
    const res = await fetch('/api/baa', { method: 'POST', headers, body: JSON.stringify(payload) }).catch(() => null);
    if (res?.ok) {
      const newBAA = await res.json();
      setBaas(prev => [newBAA, ...prev]);
      setShowCreate(false);
      setForm({ business_associate: '', contact_email: '', services: '', phi_types: '' });
      fetchAll();
    }
  }, [form, fetchAll]);

  const filtered = filter === 'all' ? baas : baas.filter(b => b.status === filter);

  return (
    <div style={{ padding: '28px 32px', color: '#f1f5f9', fontFamily: 'Inter, sans-serif', minHeight: '100vh', background: '#040812' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <div>
          <div style={{ fontSize: '0.72em', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6366f1', marginBottom: 6 }}>HIPAA Compliance</div>
          <h1 style={{ fontSize: '1.8em', fontWeight: 900, letterSpacing: '-0.03em', margin: 0 }}>Business Associate Agreements</h1>
          <p style={{ color: '#94a3b8', fontSize: '0.85em', marginTop: 4 }}>HIPAA §164.308(b) — Track BAA lifecycle: draft → sign → active → terminate</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={fetchAll} style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(99,102,241,.15)', border: '1px solid rgba(99,102,241,.3)', color: '#a5b4fc', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: '0.82em' }}>
            <RefreshCw size={13} /> Refresh
          </button>
          <button onClick={() => setShowCreate(true)} style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(99,102,241,.3)', border: '1px solid rgba(99,102,241,.5)', color: '#a5b4fc', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: '0.82em', fontWeight: 700 }}>
            <Plus size={13} /> New BAA
          </button>
        </div>
      </div>

      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 14, marginBottom: 28 }}>
          {[
            { label: 'Total BAAs', value: stats.total, color: '#a5b4fc' },
            { label: 'Active', value: stats.active, color: '#6ee7b7' },
            { label: 'Expiring Soon', value: stats.expiring_soon, color: '#fcd34d' },
            { label: 'Expired', value: stats.expired, color: '#fca5a5' },
            { label: 'Draft', value: stats.draft, color: '#94a3b8' },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 12, padding: '16px', textAlign: 'center' }}>
              <div style={{ fontSize: '2em', fontWeight: 900, color }}>{value}</div>
              <div style={{ fontSize: '0.72em', color: '#94a3b8', marginTop: 4 }}>{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Create form */}
      {showCreate && (
        <div style={{ background: 'rgba(99,102,241,.06)', border: '1px solid rgba(99,102,241,.25)', borderRadius: 14, padding: 24, marginBottom: 20 }}>
          <div style={{ fontWeight: 700, fontSize: '0.95em', marginBottom: 16 }}>New Business Associate Agreement</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
            {[
              { label: 'Business Associate Name *', key: 'business_associate', placeholder: 'Acme Corp' },
              { label: 'Contact Email', key: 'contact_email', placeholder: 'legal@acme.com' },
              { label: 'Services (comma-separated)', key: 'services', placeholder: 'EHR hosting, Data processing' },
              { label: 'PHI Types (comma-separated)', key: 'phi_types', placeholder: 'Demographics, Diagnosis codes' },
            ].map(({ label, key, placeholder }) => (
              <div key={key}>
                <div style={{ fontSize: '0.78em', color: '#94a3b8', marginBottom: 6 }}>{label}</div>
                <input value={form[key as keyof typeof form]} onChange={e => setForm(p => ({ ...p, [key]: e.target.value }))}
                  placeholder={placeholder}
                  style={{ width: '100%', background: 'rgba(255,255,255,.06)', border: '1px solid rgba(255,255,255,.12)', borderRadius: 8, padding: '8px 12px', color: '#f1f5f9', fontSize: '0.85em', outline: 'none', boxSizing: 'border-box' }} />
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowCreate(false)} style={{ background: 'transparent', border: '1px solid rgba(255,255,255,.15)', color: '#94a3b8', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: '0.82em' }}>Cancel</button>
            <button onClick={createBAA} style={{ background: 'rgba(99,102,241,.3)', border: '1px solid rgba(99,102,241,.5)', color: '#a5b4fc', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: '0.82em', fontWeight: 700 }}>Create BAA</button>
          </div>
        </div>
      )}

      {/* Filter */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {['all', 'active', 'draft', 'pending_signature', 'expired', 'terminated'].map(f => (
          <button key={f} onClick={() => setFilter(f)} style={{
            background: filter === f ? 'rgba(99,102,241,.2)' : 'transparent',
            border: '1px solid rgba(255,255,255,.1)', color: filter === f ? '#a5b4fc' : '#94a3b8',
            borderRadius: 6, padding: '5px 14px', cursor: 'pointer', fontSize: '0.78em', fontWeight: 600,
            textTransform: 'capitalize',
          }}>{f.replace('_', ' ')}</button>
        ))}
      </div>

      {/* BAA list */}
      <div style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, overflow: 'hidden' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 160px 160px 140px 120px', gap: 16, padding: '10px 20px', borderBottom: '1px solid rgba(255,255,255,.06)', fontSize: '0.72em', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          <span>Business Associate</span><span>Effective</span><span>Expires</span><span>Status</span><span></span>
        </div>
        {loading ? <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>Loading…</div>
          : filtered.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8', fontSize: '0.85em' }}>No BAAs in this category</div>
          ) : filtered.map(baa => {
            const sc = STATUS_CFG[baa.status] || STATUS_CFG.draft;
            return (
              <div key={baa.id} style={{ display: 'grid', gridTemplateColumns: '1fr 160px 160px 140px 120px', gap: 16, padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,.04)', alignItems: 'center' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.88em', display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Shield size={13} color="#6366f1" /> {baa.business_associate}
                  </div>
                  <div style={{ fontSize: '0.72em', color: '#64748b', marginTop: 2 }}>{baa.contact_email}</div>
                  <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
                    {baa.services.slice(0, 2).map(s => (
                      <span key={s} style={{ fontSize: '0.68em', background: 'rgba(99,102,241,.1)', color: '#a5b4fc', borderRadius: 4, padding: '2px 6px' }}>{s}</span>
                    ))}
                    {baa.services.length > 2 && <span style={{ fontSize: '0.68em', color: '#64748b' }}>+{baa.services.length - 2} more</span>}
                  </div>
                </div>
                <span style={{ fontSize: '0.78em', color: '#94a3b8' }}>{formatDate(baa.effective_date)}</span>
                <span style={{ fontSize: '0.78em', color: '#94a3b8' }}>{formatDate(baa.expiration_date)}</span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: sc.bg, color: sc.color, borderRadius: 20, padding: '4px 12px', fontSize: '0.72em', fontWeight: 700, width: 'fit-content' }}>
                  {baa.status === 'active' ? <CheckCircle size={10} /> : baa.status === 'expired' || baa.status === 'terminated' ? <XCircle size={10} /> : <Clock size={10} />}
                  {sc.label}
                </span>
                <div style={{ display: 'flex', gap: 6 }}>
                  {baa.status === 'draft' && (
                    <button onClick={() => sign(baa.id)} disabled={acting === baa.id}
                      style={{ background: 'rgba(16,185,129,.15)', border: '1px solid rgba(16,185,129,.3)', color: '#6ee7b7', borderRadius: 6, padding: '5px 10px', cursor: 'pointer', fontSize: '0.72em', fontWeight: 600 }}>
                      {acting === baa.id ? '…' : 'Sign'}
                    </button>
                  )}
                  {baa.status === 'active' && (
                    <button onClick={() => terminate(baa.id)} disabled={acting === baa.id}
                      style={{ background: 'rgba(239,68,68,.1)', border: '1px solid rgba(239,68,68,.25)', color: '#fca5a5', borderRadius: 6, padding: '5px 10px', cursor: 'pointer', fontSize: '0.72em', fontWeight: 600 }}>
                      {acting === baa.id ? '…' : 'Terminate'}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
      </div>
    </div>
  );
}

export default BAAManagement;
