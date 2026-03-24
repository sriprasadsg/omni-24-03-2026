import React, { useState, useEffect, useCallback } from 'react';

// Use relative path so the Vite dev-server proxy routes it to localhost:5000
const API = '/api';

// Read the auth token from whichever localStorage key the app uses
const getToken = (): string => {
    return (
        localStorage.getItem('access_token') ||
        localStorage.getItem('token') ||
        localStorage.getItem('authToken') ||
        (() => { try { return JSON.parse(localStorage.getItem('auth') || '{}').access_token || ''; } catch { return ''; } })() ||
        ''
    );
};

interface EDRAlert {
    alert_id: string;
    type: string;
    description: string;
    severity: 'critical' | 'high' | 'medium' | 'low';
    process: { pid: number; name: string; exe: string; sha256: string };
    timestamp: string;
    agent_id: string;
    hostname: string;
    acknowledged: boolean;
    requires_response: boolean;
}

interface EDRSummary {
    total_alerts_24h: number;
    unacknowledged: number;
    critical_unacknowledged: number;
    by_severity: Record<string, number>;
}

const SEVERITY_CONFIG = {
    critical: { color: '#ef4444', bg: 'rgba(239,68,68,0.12)', label: 'CRITICAL' },
    high: { color: '#f97316', bg: 'rgba(249,115,22,0.12)', label: 'HIGH' },
    medium: { color: '#eab308', bg: 'rgba(234,179,8,0.12)', label: 'MEDIUM' },
    low: { color: '#22c55e', bg: 'rgba(34,197,94,0.12)', label: 'LOW' },
};

const ACTION_OPTIONS = [
    { value: 'kill_process', label: '⚡ Kill Process', danger: true },
    { value: 'quarantine_file', label: '📦 Quarantine File', danger: true },
    { value: 'isolate_host', label: '🔒 Isolate Host', danger: true },
    { value: 'restore_host', label: '🔓 Restore Host', danger: false },
    { value: 'rollback_ransomware', label: '⏪ Ransomware Rollback (VSS)', danger: true },
];

export function EDRDashboard({ token }: { token?: string }) {
    const [alerts, setAlerts] = useState<EDRAlert[]>([]);
    const [summary, setSummary] = useState<EDRSummary | null>(null);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<'alerts' | 'response' | 'ioc'>('alerts');
    const [severityFilter, setSeverityFilter] = useState<string>('all');
    const [ackFilter, setAckFilter] = useState<'all' | 'unack'>('unack');
    const [responding, setResponding] = useState<string | null>(null);
    const [responseAgent, setResponseAgent] = useState('');
    const [responseAction, setResponseAction] = useState('kill_process');
    const [responseParam, setResponseParam] = useState('');
    const [responseHistory, setResponseHistory] = useState<any[]>([]);
    const [iocHash, setIocHash] = useState('');
    const [iocProcess, setIocProcess] = useState('');
    const [iocDesc, setIocDesc] = useState('');
    const [iocSeverity, setIocSeverity] = useState('high');
    const [iocList, setIocList] = useState<any[]>([]);
    const [feedback, setFeedback] = useState<{ msg: string; ok: boolean } | null>(null);

    const getHeaders = () => ({
        Authorization: `Bearer ${getToken()}`,
        'Content-Type': 'application/json',
    });

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const [alertsRes, summaryRes] = await Promise.all([
                fetch(`${API}/edr/alerts?acknowledged=${ackFilter === 'unack' ? 'false' : ''}&limit=100`, { headers: getHeaders() }),
                fetch(`${API}/edr/telemetry/summary`, { headers: getHeaders() }),
            ]);
            if (alertsRes.ok) setAlerts(await alertsRes.json());
            if (summaryRes.ok) setSummary(await summaryRes.json());
        } catch (e) { /* backend may not have EDR data yet */ }
        finally { setLoading(false); }
    }, [ackFilter]);

    const loadHistory = useCallback(async () => {
        try {
            const r = await fetch(`${API}/response/history?limit=50`, { headers: getHeaders() });
            if (r.ok) setResponseHistory(await r.json());
        } catch { }
    }, []);

    const loadIOC = useCallback(async () => {
        try {
            const r = await fetch(`${API}/edr/ioc`, { headers: getHeaders() });
            if (r.ok) setIocList(await r.json());
        } catch { }
    }, []);


    useEffect(() => { load(); }, [load]);
    useEffect(() => { if (activeTab === 'response') loadHistory(); }, [activeTab]);
    useEffect(() => { if (activeTab === 'ioc') loadIOC(); }, [activeTab]);

    const acknowledge = async (alertId: string) => {
        setResponding(alertId);
        try {
            await fetch(`${API}/edr/alerts/${alertId}/acknowledge`, { method: 'PATCH', headers: getHeaders() });
            setAlerts(a => a.map(al => al.alert_id === alertId ? { ...al, acknowledged: true } : al));
        } finally { setResponding(null); }
    };

    const dispatchAction = async () => {
        if (!responseAgent || !responseAction) return;
        setResponding('dispatch');
        try {
            const params: Record<string, any> = {};
            if (responseAction === 'kill_process') params.pid = parseInt(responseParam) || 0;
            if (responseAction === 'quarantine_file') params.path = responseParam;

            const r = await fetch(`${API}/response/execute`, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({
                    agent_id: responseAgent,
                    action: responseAction,
                    params,
                    reason: 'manual_operator_action',
                }),
            });
            const data = await r.json();
            setFeedback({ msg: `Task queued: ${data.task?.task_id || 'ok'}`, ok: r.ok });
            loadHistory();
        } catch (e: any) {
            setFeedback({ msg: e.message, ok: false });
        } finally {
            setResponding(null);
            setTimeout(() => setFeedback(null), 4000);
        }
    };

    const addIOC = async () => {
        if (!iocDesc) return;
        try {
            const r = await fetch(`${API}/edr/ioc`, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({ sha256: iocHash || undefined, process_name: iocProcess || undefined, description: iocDesc, severity: iocSeverity }),
            });
            if (r.ok) {
                setFeedback({ msg: 'IOC added', ok: true });
                setIocHash(''); setIocProcess(''); setIocDesc('');
                loadIOC();
                setTimeout(() => setFeedback(null), 3000);
            }
        } catch { }
    };

    const filteredAlerts = alerts.filter(a => {
        if (severityFilter !== 'all' && a.severity !== severityFilter) return false;
        return true;
    });

    return (
        <div style={{ padding: '24px', fontFamily: 'Inter, system-ui, sans-serif' }}>
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
                <div style={{ width: 40, height: 40, borderRadius: 10, background: 'linear-gradient(135deg,#ef4444,#7c3aed)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>🛡️</div>
                <div>
                    <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#0f172a' }}>Real-Time EDR Dashboard</h1>
                    <p style={{ margin: 0, fontSize: 13, color: '#64748b' }}>Endpoint Detection & Response — Powered by ETW + psutil</p>
                </div>
                <button onClick={load} style={{ marginLeft: 'auto', padding: '8px 16px', borderRadius: 8, background: '#0f172a', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 13 }}>↻ Refresh</button>
            </div>

            {/* Summary Cards */}
            {summary && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginBottom: 24 }}>
                    {[
                        { label: 'Total Alerts (24h)', value: summary.total_alerts_24h, color: '#6366f1' },
                        { label: 'Unacknowledged', value: summary.unacknowledged, color: '#f97316' },
                        { label: 'Critical (Unack)', value: summary.critical_unacknowledged, color: '#ef4444' },
                        { label: 'High Severity', value: summary.by_severity?.high || 0, color: '#eab308' },
                    ].map(card => (
                        <div key={card.label} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: '20px', boxShadow: '0 1px 4px rgba(0,0,0,0.06)' }}>
                            <div style={{ fontSize: 28, fontWeight: 700, color: card.color }}>{card.value}</div>
                            <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{card.label}</div>
                        </div>
                    ))}
                </div>
            )}

            {/* Tabs */}
            <div style={{ display: 'flex', borderBottom: '2px solid #e2e8f0', marginBottom: 20 }}>
                {(['alerts', 'response', 'ioc'] as const).map(tab => (
                    <button key={tab} onClick={() => setActiveTab(tab)} style={{
                        padding: '10px 20px', border: 'none', background: 'none', cursor: 'pointer',
                        fontSize: 14, fontWeight: activeTab === tab ? 700 : 400,
                        color: activeTab === tab ? '#6366f1' : '#64748b',
                        borderBottom: activeTab === tab ? '2px solid #6366f1' : '2px solid transparent',
                        marginBottom: -2,
                    }}>
                        {tab === 'alerts' ? '🚨 Live Alerts' : tab === 'response' ? '⚡ Response Actions' : '🔍 IOC Blocklist'}
                    </button>
                ))}
            </div>

            {/* ALERTS TAB */}
            {activeTab === 'alerts' && (
                <div>
                    {/* Filters */}
                    <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
                        <select value={severityFilter} onChange={e => setSeverityFilter(e.target.value)}
                            style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 13, background: '#fff' }}>
                            <option value="all">All Severities</option>
                            {Object.keys(SEVERITY_CONFIG).map(s => <option key={s} value={s}>{s.toUpperCase()}</option>)}
                        </select>
                        <select value={ackFilter} onChange={e => { setAckFilter(e.target.value as any); load(); }}
                            style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 13, background: '#fff' }}>
                            <option value="unack">Unacknowledged only</option>
                            <option value="all">All Alerts</option>
                        </select>
                        <span style={{ fontSize: 13, color: '#64748b', marginLeft: 'auto' }}>{filteredAlerts.length} alerts</span>
                    </div>

                    {loading ? (
                        <div style={{ textAlign: 'center', padding: 48, color: '#64748b' }}>
                            <div style={{ fontSize: 32, marginBottom: 8 }}>⏳</div>
                            Loading EDR telemetry...
                        </div>
                    ) : filteredAlerts.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: 48, background: '#f8fafc', borderRadius: 12, color: '#64748b' }}>
                            <div style={{ fontSize: 48, marginBottom: 8 }}>✅</div>
                            <div style={{ fontWeight: 600 }}>No active alerts</div>
                            <div style={{ fontSize: 13, marginTop: 4 }}>Agent EDR telemetry will appear here automatically when threats are detected.</div>
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                            {filteredAlerts.map(alert => {
                                const sev = SEVERITY_CONFIG[alert.severity] || SEVERITY_CONFIG.low;
                                return (
                                    <div key={alert.alert_id} style={{
                                        background: '#fff', border: `1px solid ${sev.color}40`, borderLeft: `4px solid ${sev.color}`,
                                        borderRadius: 10, padding: '16px 20px', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
                                    }}>
                                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                                            <span style={{ background: sev.bg, color: sev.color, padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 700, letterSpacing: 1, flexShrink: 0 }}>{sev.label}</span>
                                            <div style={{ flex: 1 }}>
                                                <div style={{ fontWeight: 600, fontSize: 14, color: '#0f172a' }}>{alert.type.replace(/_/g, ' ')}</div>
                                                <div style={{ fontSize: 13, color: '#475569', marginTop: 4 }}>{alert.description}</div>
                                                <div style={{ marginTop: 8, display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 12, color: '#94a3b8' }}>
                                                    {alert.process?.name && <span>🔧 Process: <b>{alert.process.name}</b> (PID {alert.process.pid})</span>}
                                                    {alert.hostname && <span>💻 Host: <b>{alert.hostname}</b></span>}
                                                    <span>🕐 {new Date(alert.timestamp).toLocaleString()}</span>
                                                    {alert.process?.sha256 && <span style={{ fontFamily: 'monospace' }}>SHA256: {alert.process.sha256.slice(0, 16)}…</span>}
                                                </div>
                                            </div>
                                            {!alert.acknowledged && (
                                                <button onClick={() => acknowledge(alert.alert_id)}
                                                    disabled={responding === alert.alert_id}
                                                    style={{ padding: '6px 14px', borderRadius: 8, border: '1px solid #e2e8f0', background: responding === alert.alert_id ? '#f8fafc' : '#fff', cursor: 'pointer', fontSize: 12, color: '#475569', flexShrink: 0 }}>
                                                    {responding === alert.alert_id ? '...' : '✓ Ack'}
                                                </button>
                                            )}
                                            {alert.acknowledged && <span style={{ fontSize: 11, color: '#22c55e', flexShrink: 0 }}>✓ Acknowledged</span>}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            )}

            {/* RESPONSE ACTIONS TAB */}
            {activeTab === 'response' && (
                <div style={{ display: 'grid', gridTemplateColumns: '400px 1fr', gap: 24 }}>
                    {/* Manual Action Panel */}
                    <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: 24 }}>
                        <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700, color: '#0f172a' }}>⚡ Dispatch Response Action</h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                            <div>
                                <label style={{ fontSize: 12, fontWeight: 600, color: '#64748b', display: 'block', marginBottom: 4 }}>AGENT ID</label>
                                <input value={responseAgent} onChange={e => setResponseAgent(e.target.value)}
                                    placeholder="agent-uuid or hostname"
                                    style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 13, boxSizing: 'border-box' }} />
                            </div>
                            <div>
                                <label style={{ fontSize: 12, fontWeight: 600, color: '#64748b', display: 'block', marginBottom: 4 }}>ACTION</label>
                                <select value={responseAction} onChange={e => setResponseAction(e.target.value)}
                                    style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 13 }}>
                                    {ACTION_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                                </select>
                            </div>
                            {(responseAction === 'kill_process' || responseAction === 'quarantine_file') && (
                                <div>
                                    <label style={{ fontSize: 12, fontWeight: 600, color: '#64748b', display: 'block', marginBottom: 4 }}>
                                        {responseAction === 'kill_process' ? 'PID (number)' : 'File Path'}
                                    </label>
                                    <input value={responseParam} onChange={e => setResponseParam(e.target.value)}
                                        placeholder={responseAction === 'kill_process' ? '1234' : 'C:\\path\\to\\malware.exe'}
                                        style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 13, boxSizing: 'border-box' }} />
                                </div>
                            )}
                            {feedback && (
                                <div style={{ padding: '10px 14px', borderRadius: 8, background: feedback.ok ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)', color: feedback.ok ? '#16a34a' : '#dc2626', fontSize: 13 }}>
                                    {feedback.msg}
                                </div>
                            )}
                            <button onClick={dispatchAction} disabled={responding === 'dispatch' || !responseAgent}
                                style={{ padding: '10px', borderRadius: 8, border: 'none', background: '#ef4444', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: 14, opacity: !responseAgent ? 0.5 : 1 }}>
                                {responding === 'dispatch' ? 'Dispatching...' : '🚀 Dispatch Action'}
                            </button>
                        </div>
                    </div>

                    {/* Response History */}
                    <div>
                        <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700, color: '#0f172a' }}>📋 Response History</h3>
                        {responseHistory.length === 0 ? (
                            <div style={{ textAlign: 'center', padding: 32, background: '#f8fafc', borderRadius: 12, color: '#64748b' }}>
                                No response actions dispatched yet
                            </div>
                        ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                {responseHistory.map((task, i) => (
                                    <div key={task.task_id || i} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: '14px 18px', fontSize: 13 }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                            <span style={{ fontWeight: 600, color: '#0f172a' }}>{task.action?.replace(/_/g, ' ')}</span>
                                            <span style={{ fontSize: 11, color: task.result?.success ? '#16a34a' : '#dc2626', fontWeight: 600 }}>
                                                {task.result?.success ? '✓ SUCCESS' : '✗ FAILED'}
                                            </span>
                                        </div>
                                        <div style={{ color: '#64748b', marginTop: 4 }}>Agent: {task.agent_id} • {task.executed_at ? new Date(task.executed_at).toLocaleString() : 'Pending'}</div>
                                        {task.result?.message && <div style={{ color: '#475569', marginTop: 4 }}>{task.result.message}</div>}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* IOC TAB */}
            {activeTab === 'ioc' && (
                <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: 24 }}>
                    <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: 24 }}>
                        <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700, color: '#0f172a' }}>➕ Add IOC to Blocklist</h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                            <div>
                                <label style={{ fontSize: 12, fontWeight: 600, color: '#64748b', display: 'block', marginBottom: 4 }}>SHA-256 Hash (optional)</label>
                                <input value={iocHash} onChange={e => setIocHash(e.target.value)} placeholder="abc123..."
                                    style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 13, boxSizing: 'border-box', fontFamily: 'monospace' }} />
                            </div>
                            <div>
                                <label style={{ fontSize: 12, fontWeight: 600, color: '#64748b', display: 'block', marginBottom: 4 }}>Process Name (optional)</label>
                                <input value={iocProcess} onChange={e => setIocProcess(e.target.value)} placeholder="mimikatz.exe"
                                    style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 13, boxSizing: 'border-box' }} />
                            </div>
                            <div>
                                <label style={{ fontSize: 12, fontWeight: 600, color: '#64748b', display: 'block', marginBottom: 4 }}>Description*</label>
                                <input value={iocDesc} onChange={e => setIocDesc(e.target.value)} placeholder="Credential dumper — CISA alert AA23-XXX"
                                    style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 13, boxSizing: 'border-box' }} />
                            </div>
                            <div>
                                <label style={{ fontSize: 12, fontWeight: 600, color: '#64748b', display: 'block', marginBottom: 4 }}>Severity</label>
                                <select value={iocSeverity} onChange={e => setIocSeverity(e.target.value)}
                                    style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 13 }}>
                                    {Object.keys(SEVERITY_CONFIG).map(s => <option key={s} value={s}>{s.toUpperCase()}</option>)}
                                </select>
                            </div>
                            {feedback && <div style={{ padding: '8px 12px', borderRadius: 8, background: 'rgba(34,197,94,0.1)', color: '#16a34a', fontSize: 13 }}>{feedback.msg}</div>}
                            <button onClick={addIOC} disabled={!iocDesc}
                                style={{ padding: '10px', borderRadius: 8, border: 'none', background: '#6366f1', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: 14, opacity: !iocDesc ? 0.5 : 1 }}>
                                Add to Blocklist
                            </button>
                        </div>
                    </div>
                    <div>
                        <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700, color: '#0f172a' }}>🔍 Current IOC Blocklist ({iocList.length})</h3>
                        {iocList.length === 0 ? (
                            <div style={{ textAlign: 'center', padding: 32, background: '#f8fafc', borderRadius: 12, color: '#64748b' }}>No IOCs in blocklist yet</div>
                        ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                {iocList.map((ioc, i) => {
                                    const sev = SEVERITY_CONFIG[ioc.severity as keyof typeof SEVERITY_CONFIG] || SEVERITY_CONFIG.low;
                                    return (
                                        <div key={i} style={{ background: '#fff', border: `1px solid ${sev.color}30`, borderLeft: `3px solid ${sev.color}`, borderRadius: 8, padding: '12px 16px', fontSize: 13 }}>
                                            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                                                <span style={{ background: sev.bg, color: sev.color, padding: '1px 6px', borderRadius: 4, fontSize: 10, fontWeight: 700 }}>{sev.label}</span>
                                                <span style={{ fontWeight: 600, color: '#0f172a' }}>{ioc.description}</span>
                                            </div>
                                            {ioc.sha256 && <div style={{ color: '#94a3b8', fontFamily: 'monospace', fontSize: 11, marginTop: 4 }}>SHA256: {ioc.sha256.slice(0, 32)}...</div>}
                                            {ioc.process_name && <div style={{ color: '#64748b', marginTop: 2 }}>Process: {ioc.process_name}</div>}
                                            <div style={{ color: '#94a3b8', fontSize: 11, marginTop: 2 }}>Added: {new Date(ioc.added_at).toLocaleString()}</div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
