import React, { useCallback, useEffect, useRef, useState } from 'react';
import { authFetch } from '../services/apiService';
import { socketService } from '../services/socketService';

interface Tactic { id: string; name: string; techniques: Technique[]; }
interface Technique { id: string; name: string; }
interface HeatmapCell {
    technique_id: string; technique_name: string;
    tactic_id: string; tactic_name: string;
    alert_count: number; coverage_score: number; color: string;
}
interface TechDetail {
    technique_id: string; technique_name: string; tactic_name: string;
    description: string; mitigations: string[]; data_sources: string[];
    detection: string; mitre_url: string;
}

const POLL_INTERVAL_MS = 30_000; // 30 seconds

export default function MitreAttackHeatmap() {
    const [matrix, setMatrix]       = useState<Tactic[]>([]);
    const [heatmap, setHeatmap]     = useState<HeatmapCell[]>([]);
    const [selected, setSelected]   = useState<TechDetail | null>(null);
    const [loading, setLoading]     = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [autoRefresh, setAutoRefresh] = useState(true);
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
    const [secondsAgo, setSecondsAgo]   = useState(0);

    const pollTimer   = useRef<ReturnType<typeof setInterval> | null>(null);
    const clockTimer  = useRef<ReturnType<typeof setInterval> | null>(null);
    const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // ── Fetch coverage only (matrix rarely changes) ─────────────────────────
    const fetchCoverage = useCallback(async (isInitial = false) => {
        if (!isInitial) setRefreshing(true);
        try {
            const r = await authFetch('/api/mitre/coverage');
            const data = await r.json();
            const cells: HeatmapCell[] = Array.isArray(data)
                ? data                                      // legacy shape
                : Array.isArray(data.heatmap) ? data.heatmap : [];
            setHeatmap(cells);
            setLastUpdated(new Date());
            setSecondsAgo(0);
        } catch (e) {
            console.error('[MITRE] Coverage fetch error:', e);
        } finally {
            setRefreshing(false);
        }
    }, []);

    // ── Initial load (matrix + coverage) ────────────────────────────────────
    useEffect(() => {
        let alive = true;
        (async () => {
            try {
                const [mRes, hRes] = await Promise.all([
                    authFetch('/api/mitre/matrix').then(r => r.json()),
                    authFetch('/api/mitre/coverage').then(r => r.json()),
                ]);
                if (!alive) return;
                setMatrix(mRes.tactics || []);
                const cells: HeatmapCell[] = Array.isArray(hRes)
                    ? hRes
                    : Array.isArray(hRes.heatmap) ? hRes.heatmap : [];
                setHeatmap(cells);
                setLastUpdated(new Date());
                setSecondsAgo(0);
            } finally {
                if (alive) setLoading(false);
            }
        })();
        return () => { alive = false; };
    }, []);

    // ── Polling interval ─────────────────────────────────────────────────────
    useEffect(() => {
        if (autoRefresh && !loading) {
            pollTimer.current = setInterval(() => fetchCoverage(), POLL_INTERVAL_MS);
        }
        return () => { if (pollTimer.current) clearInterval(pollTimer.current); };
    }, [autoRefresh, loading, fetchCoverage]);

    // ── "X seconds ago" clock ────────────────────────────────────────────────
    useEffect(() => {
        clockTimer.current = setInterval(() => {
            setSecondsAgo(prev => prev + 1);
        }, 1000);
        return () => { if (clockTimer.current) clearInterval(clockTimer.current); };
    }, []);

    // ── WebSocket: server pushes fresh heatmap ───────────────────────────────
    useEffect(() => {
        const onHeatmapPush = (data: { heatmap: HeatmapCell[]; timestamp: string }) => {
            if (Array.isArray(data?.heatmap)) {
                setHeatmap(data.heatmap);
                setLastUpdated(new Date());
                setSecondsAgo(0);
            }
        };
        socketService.on('mitre_heatmap_update', onHeatmapPush);
        return () => socketService.off('mitre_heatmap_update', onHeatmapPush);
    }, []);

    // ── WebSocket: new security event → debounced refresh ───────────────────
    useEffect(() => {
        const onSecurityEvent = () => {
            if (debounceRef.current) clearTimeout(debounceRef.current);
            debounceRef.current = setTimeout(() => fetchCoverage(), 3000);
        };
        socketService.on('security_event', onSecurityEvent);
        return () => {
            socketService.off('security_event', onSecurityEvent);
            if (debounceRef.current) clearTimeout(debounceRef.current);
        };
    }, [fetchCoverage]);

    // ── Helpers ──────────────────────────────────────────────────────────────
    const getCell = (techId: string) => heatmap.find(h => h.technique_id === techId);

    const showDetail = async (techId: string) => {
        const r = await authFetch(`/api/mitre/technique/${techId}`);
        setSelected(await r.json());
    };

    const exportNavigator = async () => {
        const r = await authFetch('/api/mitre/navigator-export');
        const blob = await r.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'attack-layer.json';
        a.click();
    };

    const manualRefresh = async () => {
        if (refreshing) return;
        await fetchCoverage();
        // also trigger WebSocket push via backend
        authFetch('/api/mitre/coverage/refresh', { method: 'POST' }).catch(() => {});
    };

    const formatAgo = (s: number) => {
        if (s < 60) return `${s}s ago`;
        return `${Math.floor(s / 60)}m ${s % 60}s ago`;
    };

    const totalCovered = heatmap.filter(h => h.alert_count > 0).length;
    const totalTech    = heatmap.length;

    if (loading) return (
        <div style={{ color: '#94a3b8', padding: 40, textAlign: 'center', background: '#0f172a', minHeight: '100vh' }}>
            Loading ATT&CK matrix…
        </div>
    );

    return (
        <div style={{ background: '#0f172a', minHeight: '100vh', color: '#f1f5f9', padding: 24 }}>

            {/* ── Header ── */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <div>
                    <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, background: 'linear-gradient(135deg,#7c3aed,#ef4444)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                        MITRE ATT&CK® Heatmap
                    </h1>
                    <p style={{ color: '#64748b', margin: '4px 0 0' }}>Enterprise Matrix — Detection Coverage View</p>
                </div>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                    <div style={{ background: '#1e293b', borderRadius: 10, padding: '8px 16px', textAlign: 'center' }}>
                        <div style={{ fontSize: 22, fontWeight: 800, color: totalCovered > 0 ? '#7c3aed' : '#ef4444' }}>
                            {totalCovered}/{totalTech}
                        </div>
                        <div style={{ fontSize: 11, color: '#64748b' }}>Techniques detected</div>
                    </div>
                    <button onClick={exportNavigator}
                        style={{ background: 'linear-gradient(135deg,#7c3aed,#6d28d9)', color: 'white', border: 'none', borderRadius: 8, padding: '10px 18px', cursor: 'pointer', fontWeight: 600 }}>
                        ⬇ Export Navigator Layer
                    </button>
                </div>
            </div>

            {/* ── Auto-refresh controls ── */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16, padding: '8px 14px', background: '#1e293b', borderRadius: 8, border: '1px solid #334155', width: 'fit-content' }}>
                {/* Live badge */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{
                        width: 8, height: 8, borderRadius: '50%',
                        background: autoRefresh ? '#22c55e' : '#475569',
                        boxShadow: autoRefresh ? '0 0 0 3px rgba(34,197,94,0.25)' : 'none',
                        display: 'inline-block',
                        animation: autoRefresh ? 'pulse 2s infinite' : 'none',
                    }} />
                    <span style={{ fontSize: 12, fontWeight: 700, color: autoRefresh ? '#22c55e' : '#475569' }}>
                        {autoRefresh ? 'LIVE' : 'PAUSED'}
                    </span>
                </div>

                {/* Last updated */}
                <span style={{ fontSize: 11, color: '#64748b' }}>
                    {lastUpdated ? `Updated ${formatAgo(secondsAgo)}` : 'Never updated'}
                </span>

                {/* Refresh spinner */}
                {refreshing && (
                    <span style={{ fontSize: 11, color: '#7c3aed' }}>↻ Refreshing…</span>
                )}

                {/* Toggle auto-refresh */}
                <button
                    onClick={() => setAutoRefresh(v => !v)}
                    style={{
                        fontSize: 11, padding: '3px 10px', borderRadius: 6, cursor: 'pointer', fontWeight: 600,
                        background: autoRefresh ? 'rgba(239,68,68,0.15)' : 'rgba(34,197,94,0.15)',
                        color: autoRefresh ? '#ef4444' : '#22c55e',
                        border: `1px solid ${autoRefresh ? '#ef4444' : '#22c55e'}`,
                    }}>
                    {autoRefresh ? 'Pause' : 'Resume'}
                </button>

                {/* Manual refresh */}
                <button
                    onClick={manualRefresh}
                    disabled={refreshing}
                    style={{
                        fontSize: 11, padding: '3px 10px', borderRadius: 6, cursor: refreshing ? 'not-allowed' : 'pointer',
                        fontWeight: 600, background: 'rgba(124,58,237,0.15)', color: '#a78bfa',
                        border: '1px solid #7c3aed', opacity: refreshing ? 0.5 : 1,
                    }}>
                    ↻ Refresh Now
                </button>

                <span style={{ fontSize: 10, color: '#475569' }}>Auto-refresh every 30s</span>
            </div>

            {/* ── Legend ── */}
            <div style={{ display: 'flex', gap: 16, marginBottom: 20 }}>
                {([['#1e293b', 'No coverage'], ['#7c3aed', '1–4 alerts'], ['#f97316', '5–9 alerts'], ['#ef4444', '10+ alerts']] as [string, string][]).map(([color, label]) => (
                    <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div style={{ width: 14, height: 14, borderRadius: 3, background: color, border: '1px solid #334155' }} />
                        <span style={{ fontSize: 12, color: '#94a3b8' }}>{label}</span>
                    </div>
                ))}
            </div>

            {/* ── Matrix grid ── */}
            <div style={{ overflowX: 'auto', paddingBottom: 8 }}>
                <div style={{ display: 'flex', gap: 8, minWidth: 1200 }}>
                    {matrix.map(tactic => (
                        <div key={tactic.id} style={{ flex: 1, minWidth: 120 }}>
                            <div style={{ background: '#1e293b', borderRadius: 6, padding: '6px 8px', marginBottom: 6, textAlign: 'center', fontSize: 11, fontWeight: 700, color: '#a78bfa', border: '1px solid #334155' }}>
                                {tactic.name}
                            </div>
                            {tactic.techniques.map(tech => {
                                const cell = getCell(tech.id);
                                return (
                                    <div key={tech.id}
                                        onClick={() => showDetail(tech.id)}
                                        title={`${tech.id}: ${tech.name}\n${cell?.alert_count || 0} alerts`}
                                        style={{
                                            background: cell?.color || '#1e293b',
                                            borderRadius: 4, padding: '5px 6px', marginBottom: 4,
                                            cursor: 'pointer', fontSize: 10,
                                            color: cell?.alert_count ? '#fff' : '#475569',
                                            border: selected?.technique_id === tech.id ? '2px solid #f1f5f9' : '1px solid transparent',
                                            transition: 'transform 0.1s',
                                            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                        }}
                                        onMouseEnter={e => (e.currentTarget.style.transform = 'scale(1.03)')}
                                        onMouseLeave={e => (e.currentTarget.style.transform = 'scale(1)')}
                                    >
                                        <div style={{ fontWeight: 600, fontSize: 9, color: 'rgba(245,245,245,0.6)' }}>{tech.id}</div>
                                        <div>{tech.name}</div>
                                        {cell && cell.alert_count > 0 && (
                                            <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.7)', marginTop: 1 }}>
                                                {cell.alert_count} alert{cell.alert_count !== 1 ? 's' : ''}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    ))}
                </div>
            </div>

            {/* ── Detail side panel ── */}
            {selected && (
                <div style={{ position: 'fixed', right: 0, top: 0, bottom: 0, width: 380, background: '#1e293b', borderLeft: '1px solid #334155', padding: 24, overflowY: 'auto', zIndex: 100 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                        <div>
                            <div style={{ fontSize: 12, color: '#7c3aed', fontWeight: 700 }}>{selected.technique_id}</div>
                            <h3 style={{ margin: '4px 0 0', fontSize: 18 }}>{selected.technique_name}</h3>
                            <div style={{ fontSize: 12, color: '#64748b' }}>{selected.tactic_name}</div>
                        </div>
                        <button onClick={() => setSelected(null)} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: 20 }}>✕</button>
                    </div>
                    <p style={{ color: '#94a3b8', fontSize: 14, lineHeight: 1.6 }}>{selected.description}</p>
                    {selected.mitigations?.length > 0 && (
                        <div style={{ marginBottom: 16 }}>
                            <h4 style={{ color: '#22c55e', margin: '0 0 8px', fontSize: 13 }}>🛡 Mitigations</h4>
                            {selected.mitigations.map((m, i) => (
                                <div key={i} style={{ color: '#94a3b8', fontSize: 13, padding: '4px 0', borderBottom: '1px solid #0f172a' }}>{m}</div>
                            ))}
                        </div>
                    )}
                    {selected.detection && (
                        <div style={{ background: 'rgba(124,58,237,0.1)', border: '1px solid #7c3aed', borderRadius: 8, padding: 12, marginBottom: 16 }}>
                            <h4 style={{ color: '#a78bfa', margin: '0 0 6px', fontSize: 13 }}>🔍 Detection Guidance</h4>
                            <p style={{ color: '#94a3b8', fontSize: 13, margin: 0 }}>{selected.detection}</p>
                        </div>
                    )}
                    <a href={selected.mitre_url} target="_blank" rel="noopener noreferrer"
                        style={{ color: '#7c3aed', fontSize: 13, textDecoration: 'none' }}>
                        View on MITRE ATT&CK →
                    </a>
                </div>
            )}

            <style>{`
                @keyframes pulse {
                    0%, 100% { opacity: 1; }
                    50%       { opacity: 0.4; }
                }
            `}</style>
        </div>
    );
}
