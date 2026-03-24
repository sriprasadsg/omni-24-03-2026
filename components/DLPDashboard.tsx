import React, { useEffect, useState, useRef } from 'react';

const API = '/api';
function getHeaders(): HeadersInit {
    const keys = ['access_token', 'token', 'authToken'];
    let t = ''; for (const k of keys) { t = localStorage.getItem(k) || ''; if (t) break; }
    return { 'Content-Type': 'application/json', ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}

interface Incident { scan_id: string; filename: string; finding_count: number; sensitivity: string; status: string; scanned_at: string; findings: any[]; }
interface Policy { policy_id: string; name: string; pattern: string; severity: string; enabled: boolean; }

const SEV_COLOR: Record<string, string> = { critical: '#ef4444', high: '#f97316', medium: '#eab308', low: '#22c55e' };
const SENS_COLOR: Record<string, string> = { restricted: '#ef4444', confidential: '#f97316', internal: '#eab308', public: '#22c55e' };

export default function DLPDashboard() {
    const [incidents, setIncidents] = useState<Incident[]>([]);
    const [policies, setPolicies] = useState<Policy[]>([]);
    const [tab, setTab] = useState<'incidents' | 'scan' | 'policies'>('incidents');
    const [scanResult, setScanResult] = useState<any>(null);
    const [scanning, setScanning] = useState(false);
    const [newPolicy, setNewPolicy] = useState({ name: '', pattern: '', severity: 'medium' });
    const [saving, setSaving] = useState(false);
    const [feedback, setFeedback] = useState<{ msg: string; ok: boolean } | null>(null);
    const fileRef = useRef<HTMLInputElement>(null);

    const load = async () => {
        const [r1, r2] = await Promise.all([
            fetch(`${API}/dlp/incidents`, { headers: getHeaders() }).then(r => r.json()),
            fetch(`${API}/dlp/policies`, { headers: getHeaders() }).then(r => r.json()),
        ]);
        setIncidents(Array.isArray(r1) ? r1 : []);
        setPolicies(Array.isArray(r2) ? r2 : []);
    };
    useEffect(() => { load(); }, []);

    const scanFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]; if (!file) return;
        setScanning(true); setScanResult(null);
        const form = new FormData(); form.append('file', file);
        const token = localStorage.getItem('access_token') || localStorage.getItem('token') || '';
        const r = await fetch(`${API}/dlp/scan`, { method: 'POST', headers: token ? { Authorization: `Bearer ${token}` } : {}, body: form });
        const d = await r.json();
        setScanResult(d); setScanning(false);
        if (d.finding_count > 0) load();
    };

    const resolve = async (scanId: string) => {
        await fetch(`${API}/dlp/incidents/${scanId}/resolve`, { method: 'PATCH', headers: getHeaders() });
        load();
    };

    const addPolicy = async () => {
        if (!newPolicy.name || !newPolicy.pattern) return;
        setSaving(true);
        const r = await fetch(`${API}/dlp/policies`, { method: 'POST', headers: getHeaders(), body: JSON.stringify(newPolicy) });
        const d = await r.json();
        setFeedback({ msg: d.success ? 'Policy created' : (d.detail || 'Error'), ok: !!d.success });
        setTimeout(() => setFeedback(null), 3000);
        if (d.success) { setNewPolicy({ name: '', pattern: '', severity: 'medium' }); load(); }
        setSaving(false);
    };

    const tabs = [
        { id: 'incidents', label: `🚨 Incidents (${incidents.filter(i => i.status === 'open').length})` },
        { id: 'scan', label: '🔍 Scan File' },
        { id: 'policies', label: `📋 Policies (${policies.length})` },
    ];

    return (
        <div style={{ background: '#0f172a', minHeight: '100vh', color: '#f1f5f9', padding: 24 }}>
            <div style={{ marginBottom: 24 }}>
                <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, background: 'linear-gradient(135deg,#f97316,#ef4444)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>Data Loss Prevention</h1>
                <p style={{ color: '#64748b', margin: '4px 0 0' }}>PII detection, sensitive data classification, and bulk export monitoring</p>
            </div>

            {/* Summary cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginBottom: 24 }}>
                {[
                    { label: 'Open Incidents', val: incidents.filter(i => i.status === 'open').length, color: '#ef4444' },
                    { label: 'Resolved', val: incidents.filter(i => i.status === 'resolved').length, color: '#22c55e' },
                    { label: 'Critical Findings', val: incidents.reduce((acc, i) => acc + i.findings.filter((f: any) => f.severity === 'critical').length, 0), color: '#ef4444' },
                    { label: 'Active Policies', val: policies.filter(p => p.enabled).length, color: '#7c3aed' },
                ].map(c => (
                    <div key={c.label} style={{ background: '#1e293b', borderRadius: 12, padding: '16px 20px', border: '1px solid #334155' }}>
                        <div style={{ fontSize: 28, fontWeight: 800, color: c.color }}>{c.val}</div>
                        <div style={{ color: '#64748b', fontSize: 13 }}>{c.label}</div>
                    </div>
                ))}
            </div>

            {/* Tabs */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
                {tabs.map(t => (
                    <button key={t.id} onClick={() => setTab(t.id as any)}
                        style={{
                            padding: '8px 20px', borderRadius: 8, border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: 14,
                            background: tab === t.id ? '#7c3aed' : '#1e293b', color: tab === t.id ? 'white' : '#94a3b8'
                        }}>
                        {t.label}
                    </button>
                ))}
            </div>

            {/* Incidents tab */}
            {tab === 'incidents' && (
                <div>
                    {incidents.length === 0 && <div style={{ color: '#64748b', textAlign: 'center', padding: 40 }}>No DLP incidents found.</div>}
                    {incidents.map(inc => (
                        <div key={inc.scan_id} style={{ background: '#1e293b', borderRadius: 12, padding: 20, marginBottom: 12, border: '1px solid #334155' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                                <div>
                                    <div style={{ fontWeight: 700, fontSize: 16 }}>📄 {inc.filename}</div>
                                    <div style={{ color: '#64748b', fontSize: 12 }}>{new Date(inc.scanned_at).toLocaleString()}</div>
                                </div>
                                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                                    <span style={{ background: SENS_COLOR[inc.sensitivity] + '33', color: SENS_COLOR[inc.sensitivity], padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 700 }}>
                                        {inc.sensitivity.toUpperCase()}
                                    </span>
                                    <span style={{ background: inc.status === 'open' ? '#ef444422' : '#22c55e22', color: inc.status === 'open' ? '#ef4444' : '#22c55e', padding: '3px 10px', borderRadius: 20, fontSize: 12 }}>
                                        {inc.status}
                                    </span>
                                </div>
                            </div>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
                                {inc.findings.map((f: any, i: number) => (
                                    <span key={i} style={{ background: SEV_COLOR[f.severity] + '22', color: SEV_COLOR[f.severity], padding: '4px 10px', borderRadius: 20, fontSize: 12 }}>
                                        {f.name} — {f.redacted_value}
                                    </span>
                                ))}
                            </div>
                            {inc.status === 'open' && (
                                <button onClick={() => resolve(inc.scan_id)}
                                    style={{ background: '#334155', color: '#94a3b8', border: 'none', borderRadius: 6, padding: '6px 16px', cursor: 'pointer', fontSize: 13 }}>
                                    ✓ Mark Resolved
                                </button>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {/* Scan tab */}
            {tab === 'scan' && (
                <div style={{ maxWidth: 600 }}>
                    <div
                        onClick={() => fileRef.current?.click()}
                        style={{ cursor: 'pointer', background: '#1e293b', borderRadius: 12, padding: 32, border: '2px dashed #334155', textAlign: 'center', marginBottom: 24 }}>
                        <div style={{ fontSize: 48, marginBottom: 12 }}>📁</div>
                        <p style={{ color: '#94a3b8', margin: 0 }}>Click or drag a file to scan for PII and sensitive data</p>
                        <p style={{ color: '#475569', fontSize: 12, margin: '8px 0 0' }}>Supports .txt, .csv, .json, .xml, .log and other text-based files</p>
                        <input ref={fileRef} type="file" accept=".txt,.csv,.json,.xml,.log,.py,.js,.ts,.yaml,.yml,.env" onChange={scanFile} style={{ display: 'none' }} />
                    </div>
                    {scanning && <div style={{ color: '#7c3aed', textAlign: 'center', padding: 20 }}>🔍 Scanning for PII...</div>}
                    {scanResult && (
                        <div style={{ background: '#1e293b', borderRadius: 12, padding: 24, border: `1px solid ${scanResult.finding_count ? '#ef4444' : '#22c55e'}` }}>
                            <h3 style={{ color: scanResult.finding_count ? '#ef4444' : '#22c55e', margin: '0 0 16px' }}>
                                {scanResult.finding_count ? `⚠️ ${scanResult.finding_count} PII finding(s) detected` : '✅ No PII detected'}
                            </h3>
                            <div style={{ color: '#64748b', fontSize: 13, marginBottom: 16 }}>
                                Sensitivity: <strong style={{ color: SENS_COLOR[scanResult.sensitivity] }}>{scanResult.sensitivity?.toUpperCase()}</strong>
                            </div>
                            {scanResult.findings?.map((f: any, i: number) => (
                                <div key={i} style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid #ef4444', borderRadius: 8, padding: 12, marginBottom: 8 }}>
                                    <div style={{ fontWeight: 700, color: '#ef4444' }}>{f.name}</div>
                                    <div style={{ color: '#94a3b8', fontSize: 13 }}>Redacted: <code>{f.redacted_value}</code></div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* Policies tab */}
            {tab === 'policies' && (
                <div>
                    <div style={{ background: '#1e293b', borderRadius: 12, padding: 24, marginBottom: 20, border: '1px solid #334155' }}>
                        <h3 style={{ margin: '0 0 16px', fontSize: 16 }}>Add Custom DLP Policy</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr auto', gap: 12, alignItems: 'end' }}>
                            <div>
                                <label style={{ color: '#94a3b8', fontSize: 12, display: 'block', marginBottom: 4 }}>Policy Name</label>
                                <input value={newPolicy.name} onChange={e => setNewPolicy(p => ({ ...p, name: e.target.value }))}
                                    style={{ width: '100%', padding: 10, background: '#0f172a', border: '1px solid #334155', borderRadius: 8, color: '#f1f5f9', boxSizing: 'border-box' }} placeholder="e.g. NHS Patient ID" />
                            </div>
                            <div>
                                <label style={{ color: '#94a3b8', fontSize: 12, display: 'block', marginBottom: 4 }}>Regex Pattern</label>
                                <input value={newPolicy.pattern} onChange={e => setNewPolicy(p => ({ ...p, pattern: e.target.value }))}
                                    style={{ width: '100%', padding: 10, background: '#0f172a', border: '1px solid #334155', borderRadius: 8, color: '#f1f5f9', boxSizing: 'border-box', fontFamily: 'monospace' }} placeholder="\b\d{3} \d{3} \d{4}\b" />
                            </div>
                            <button onClick={addPolicy} disabled={saving}
                                style={{ padding: '10px 20px', background: '#7c3aed', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600 }}>
                                {saving ? 'Saving...' : '+ Add'}
                            </button>
                        </div>
                        {feedback && <div style={{ marginTop: 12, color: feedback.ok ? '#22c55e' : '#ef4444' }}>{feedback.msg}</div>}
                    </div>
                    {policies.map(p => (
                        <div key={p.policy_id} style={{ background: '#1e293b', borderRadius: 10, padding: 16, marginBottom: 8, border: '1px solid #334155', display: 'flex', justifyContent: 'space-between' }}>
                            <div>
                                <div style={{ fontWeight: 600 }}>{p.name}</div>
                                <code style={{ color: '#64748b', fontSize: 12 }}>{p.pattern}</code>
                            </div>
                            <span style={{ color: SEV_COLOR[p.severity], padding: '3px 12px', background: SEV_COLOR[p.severity] + '22', borderRadius: 20, fontSize: 12, fontWeight: 700, alignSelf: 'center' }}>
                                {p.severity}
                            </span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
