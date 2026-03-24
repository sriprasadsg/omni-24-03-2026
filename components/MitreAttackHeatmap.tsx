import React, { useEffect, useState } from 'react';

const API = '/api';
function getHeaders(): HeadersInit {
    const keys = ['access_token', 'token', 'authToken'];
    let token = '';
    for (const k of keys) { token = localStorage.getItem(k) || ''; if (token) break; }
    return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

interface Tactic { id: string; name: string; techniques: Technique[]; }
interface Technique { id: string; name: string; }
interface HeatmapCell {
    technique_id: string; technique_name: string;
    tactic_id: string; tactic_name: string;
    alert_count: number; coverage_score: number; color: string;
}
interface TechDetail { technique_id: string; technique_name: string; tactic_name: string; description: string; mitigations: string[]; data_sources: string[]; detection: string; mitre_url: string; }

export default function MitreAttackHeatmap() {
    const [matrix, setMatrix] = useState<Tactic[]>([]);
    const [heatmap, setHeatmap] = useState<HeatmapCell[]>([]);
    const [selected, setSelected] = useState<TechDetail | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        Promise.all([
            fetch(`${API}/mitre/matrix`, { headers: getHeaders() }).then(r => r.json()),
            fetch(`${API}/mitre/coverage`, { headers: getHeaders() }).then(r => r.json()),
        ]).then(([m, h]) => {
            setMatrix(m.tactics || []);
            setHeatmap(Array.isArray(h) ? h : []);
        }).finally(() => setLoading(false));
    }, []);

    const getCell = (techId: string) => heatmap.find(h => h.technique_id === techId);

    const showDetail = async (techId: string) => {
        const r = await fetch(`${API}/mitre/technique/${techId}`, { headers: getHeaders() });
        const d = await r.json();
        setSelected(d);
    };

    const exportNavigator = async () => {
        const r = await fetch(`${API}/mitre/navigator-export`, { headers: getHeaders() });
        const blob = await r.blob();
        const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
        a.download = 'attack-layer.json'; a.click();
    };

    const totalCovered = heatmap.filter(h => h.alert_count > 0).length;
    const totalTech = heatmap.length;

    if (loading) return <div style={{ color: '#94a3b8', padding: 40, textAlign: 'center' }}>Loading ATT&CK matrix...</div>;

    return (
        <div style={{ background: '#0f172a', minHeight: '100vh', color: '#f1f5f9', padding: 24 }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <div>
                    <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, background: 'linear-gradient(135deg,#7c3aed,#ef4444)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>MITRE ATT&CK® Heatmap</h1>
                    <p style={{ color: '#64748b', margin: '4px 0 0' }}>Enterprise Matrix — Detection Coverage View</p>
                </div>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                    {/* Coverage stat */}
                    <div style={{ background: '#1e293b', borderRadius: 10, padding: '8px 16px', textAlign: 'center' }}>
                        <div style={{ fontSize: 22, fontWeight: 800, color: totalCovered > 0 ? '#7c3aed' : '#ef4444' }}>{totalCovered}/{totalTech}</div>
                        <div style={{ fontSize: 11, color: '#64748b' }}>Techniques with detections</div>
                    </div>
                    <button onClick={exportNavigator}
                        style={{ background: 'linear-gradient(135deg,#7c3aed,#6d28d9)', color: 'white', border: 'none', borderRadius: 8, padding: '10px 18px', cursor: 'pointer', fontWeight: 600 }}>
                        ⬇ Export Navigator Layer
                    </button>
                </div>
            </div>

            {/* Legend */}
            <div style={{ display: 'flex', gap: 16, marginBottom: 20 }}>
                {[['#1e293b', 'No coverage'], ['#7c3aed', '1-4 alerts'], ['#f97316', '5-9 alerts'], ['#ef4444', '10+ alerts']].map(([color, label]) => (
                    <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div style={{ width: 14, height: 14, borderRadius: 3, background: color, border: '1px solid #334155' }} />
                        <span style={{ fontSize: 12, color: '#94a3b8' }}>{label}</span>
                    </div>
                ))}
            </div>

            {/* Matrix grid */}
            <div style={{ overflowX: 'auto', paddingBottom: 8 }}>
                <div style={{ display: 'flex', gap: 8, minWidth: 1200 }}>
                    {matrix.map(tactic => (
                        <div key={tactic.id} style={{ flex: 1, minWidth: 120 }}>
                            {/* Tactic header */}
                            <div style={{ background: '#1e293b', borderRadius: 6, padding: '6px 8px', marginBottom: 6, textAlign: 'center', fontSize: 11, fontWeight: 700, color: '#a78bfa', border: '1px solid #334155' }}>
                                {tactic.name}
                            </div>
                            {/* Techniques */}
                            {tactic.techniques.map(tech => {
                                const cell = getCell(tech.id);
                                const bg = cell?.color || '#1e293b';
                                return (
                                    <div key={tech.id}
                                        onClick={() => showDetail(tech.id)}
                                        title={`${tech.id}: ${tech.name}\n${cell?.alert_count || 0} alerts`}
                                        style={{
                                            background: bg, borderRadius: 4, padding: '5px 6px', marginBottom: 4,
                                            cursor: 'pointer', fontSize: 10, color: cell?.alert_count ? '#fff' : '#475569',
                                            border: selected?.technique_id === tech.id ? '2px solid #f1f5f9' : '1px solid transparent',
                                            transition: 'transform 0.1s', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                        }}
                                        onMouseEnter={e => (e.currentTarget.style.transform = 'scale(1.03)')}
                                        onMouseLeave={e => (e.currentTarget.style.transform = 'scale(1)')}
                                    >
                                        <div style={{ fontWeight: 600, fontSize: 9, color: 'rgba(245,245,245,0.6)' }}>{tech.id}</div>
                                        <div>{tech.name}</div>
                                    </div>
                                );
                            })}
                        </div>
                    ))}
                </div>
            </div>

            {/* Detail side panel */}
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
                            {selected.mitigations.map((m, i) => <div key={i} style={{ color: '#94a3b8', fontSize: 13, padding: '4px 0', borderBottom: '1px solid #0f172a' }}>{m}</div>)}
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
        </div>
    );
}
