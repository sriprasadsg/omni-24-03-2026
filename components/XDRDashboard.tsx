import React, { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../services/apiService';

const API = '/api';

interface Correlation {
    id?: string;
    type: string;
    pattern?: string;
    severity: 'critical' | 'high' | 'medium' | 'low';
    confidence: number;
    event_count: number;
    time_window_minutes: number;
    description?: string;
    entities?: string[];
    tenant_id?: string;
    detected_at: string;
    auto_responded?: boolean;
    playbooks_triggered?: string[];
}

interface XdrHunts {
    findingsLast24h: number;
    confirmedThreats: number;
    activeHunts: number;
    falsePositives: number;
}

const SEVERITY_PALETTE: Record<string, { bg: string; text: string; border: string }> = {
    critical: { bg: 'bg-red-50 dark:bg-red-900/20', text: 'text-red-700 dark:text-red-300', border: 'border-red-200 dark:border-red-800' },
    high: { bg: 'bg-orange-50 dark:bg-orange-900/20', text: 'text-orange-700 dark:text-orange-300', border: 'border-orange-200 dark:border-orange-800' },
    medium: { bg: 'bg-yellow-50 dark:bg-yellow-900/20', text: 'text-yellow-700 dark:text-yellow-300', border: 'border-yellow-200 dark:border-yellow-800' },
    low: { bg: 'bg-blue-50 dark:bg-blue-900/20', text: 'text-blue-700 dark:text-blue-300', border: 'border-blue-200 dark:border-blue-800' },
};

const PATTERN_META: Record<string, { icon: string; label: string; tactic: string }> = {
    credential_access: { icon: '🔑', label: 'Credential Access', tactic: 'TA0006' },
    lateral_movement: { icon: '↔️', label: 'Lateral Movement', tactic: 'TA0008' },
    data_exfiltration: { icon: '📤', label: 'Data Exfiltration', tactic: 'TA0010' },
    privilege_escalation: { icon: '⬆️', label: 'Privilege Escalation', tactic: 'TA0004' },
    ransomware: { icon: '🔒', label: 'Ransomware', tactic: 'T1486' },
    time_based: { icon: '⏱️', label: 'High-Frequency Events', tactic: 'TA0001' },
    entity_based: { icon: '🌐', label: 'Entity Correlation', tactic: 'TA0002' },
};

const ConfidenceMeter: React.FC<{ value: number }> = ({ value }) => {
    const pct = Math.round(value * 100);
    const color = pct >= 80 ? '#ef4444' : pct >= 50 ? '#f97316' : '#eab308';
    return (
        <div className="flex items-center gap-2">
            <div className="flex-1 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: color }} />
            </div>
            <span className="text-xs font-bold tabular-nums" style={{ color }}>{pct}%</span>
        </div>
    );
};

export const XDRDashboard: React.FC = () => {
    const [correlations, setCorrelations] = useState<Correlation[]>([]);
    const [hunts, setHunts] = useState<XdrHunts | null>(null);
    const [activeTab, setActiveTab] = useState<'overview' | 'correlations' | 'hunt' | 'patterns'>('overview');
    const [loading, setLoading] = useState(true);
    const [analyzing, setAnalyzing] = useState(false);
    const [severityFilter, setSeverityFilter] = useState<string>('all');
    const [feedback, setFeedback] = useState<{ msg: string; ok: boolean } | null>(null);

    const flash = (msg: string, ok: boolean) => {
        setFeedback({ msg, ok });
        setTimeout(() => setFeedback(null), 4000);
    };

    const loadAll = useCallback(async () => {
        setLoading(true);
        try {
            const [corrRes, huntsRes] = await Promise.all([
                authFetch(`${API}/correlations`),
                authFetch(`${API}/xdr/automated-hunts`),
            ]);
            if (corrRes.ok) setCorrelations(await corrRes.json());
            if (huntsRes.ok) setHunts(await huntsRes.json());
        } catch { }
        finally { setLoading(false); }
    }, []);

    useEffect(() => { loadAll(); }, [loadAll]);

    const runAnalysis = async () => {
        setAnalyzing(true);
        try {
            const r = await authFetch(`${API}/correlations/analyze`, {
                method: 'POST',
                body: JSON.stringify({ time_window_minutes: 60 }),
            });
            const data = await r.json();
            flash(`Analysis complete: ${Array.isArray(data) ? data.length : 0} correlation(s) detected`, r.ok);
            loadAll();
        } catch (e: any) { flash(e.message, false); }
        finally { setAnalyzing(false); }
    };

    const filtered = correlations.filter(c => severityFilter === 'all' || c.severity === severityFilter);

    // Derived stats
    const criticalCount = correlations.filter(c => c.severity === 'critical').length;
    const highCount = correlations.filter(c => c.severity === 'high').length;
    const autoResponded = correlations.filter(c => c.auto_responded).length;
    const patternBreakdown = correlations.reduce((acc: Record<string, number>, c) => {
        const key = c.pattern || c.type || 'unknown';
        acc[key] = (acc[key] || 0) + 1;
        return acc;
    }, {});

    const TABS = [
        { id: 'overview', label: 'Overview' },
        { id: 'correlations', label: `Correlations (${correlations.length})` },
        { id: 'hunt', label: 'Automated Hunts' },
        { id: 'patterns', label: 'Attack Patterns' },
    ] as const;

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-cyan-600 to-blue-700 flex items-center justify-center text-white text-2xl shadow-lg shadow-cyan-500/25">
                    🌐
                </div>
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white">XDR — Extended Detection & Response</h1>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Cross-domain telemetry correlation · MITRE ATT&CK intelligence · Auto-response loop</p>
                </div>
                <div className="ml-auto flex gap-2">
                    <button onClick={runAnalysis} disabled={analyzing}
                        className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-700 disabled:opacity-50 text-white text-sm font-medium transition-colors">
                        {analyzing ? '⏳ Analyzing…' : '⚡ Run Correlation Analysis'}
                    </button>
                    <button onClick={loadAll} className="px-4 py-2 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-sm font-medium hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors">
                        ↻
                    </button>
                </div>
            </div>

            {feedback && (
                <div className={`px-4 py-3 rounded-lg text-sm font-medium ${feedback.ok ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-800' : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800'}`}>
                    {feedback.msg}
                </div>
            )}

            {/* KPI Row */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {[
                    { label: 'Total Correlations', value: correlations.length, sub: 'detected patterns', color: 'from-cyan-500 to-cyan-600' },
                    { label: 'Critical / High', value: `${criticalCount} / ${highCount}`, sub: 'severity breakdown', color: 'from-red-500 to-red-600' },
                    { label: 'Auto-Responded', value: autoResponded, sub: 'playbooks triggered', color: 'from-green-500 to-green-600' },
                    { label: 'Active Hunts', value: loading ? '—' : (hunts?.activeHunts ?? 0), sub: 'automated threat hunts', color: 'from-blue-500 to-blue-600' },
                ].map(card => (
                    <div key={card.label} className={`bg-gradient-to-br ${card.color} rounded-xl p-4 text-white shadow-md`}>
                        <div className="text-3xl font-bold">{loading ? '—' : card.value}</div>
                        <div className="text-xs font-semibold mt-1 opacity-90">{card.label}</div>
                        <div className="text-xs mt-0.5 opacity-70">{card.sub}</div>
                    </div>
                ))}
            </div>

            {/* Tabs */}
            <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
                {TABS.map(tab => (
                    <button key={tab.id} onClick={() => setActiveTab(tab.id as any)}
                        className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${activeTab === tab.id ? 'bg-cyan-600 text-white' : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100'}`}>
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* Overview Tab */}
            {activeTab === 'overview' && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Severity Distribution */}
                    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
                        <h2 className="text-base font-semibold text-gray-900 dark:text-white mb-4">Severity Distribution</h2>
                        <div className="space-y-3">
                            {(['critical', 'high', 'medium', 'low'] as const).map(sev => {
                                const count = correlations.filter(c => c.severity === sev).length;
                                const pct = correlations.length ? Math.round((count / correlations.length) * 100) : 0;
                                const pal = SEVERITY_PALETTE[sev];
                                return (
                                    <div key={sev}>
                                        <div className="flex justify-between text-sm mb-1">
                                            <span className={`capitalize font-medium ${pal.text}`}>{sev}</span>
                                            <span className="text-gray-500 dark:text-gray-400">{count} ({pct}%)</span>
                                        </div>
                                        <div className="h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                                            <div className={`h-full rounded-full ${sev === 'critical' ? 'bg-red-500' : sev === 'high' ? 'bg-orange-500' : sev === 'medium' ? 'bg-yellow-500' : 'bg-blue-500'}`}
                                                style={{ width: `${pct}%` }} />
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    {/* Latest Correlations */}
                    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
                        <h2 className="text-base font-semibold text-gray-900 dark:text-white mb-4">Latest Detections</h2>
                        <div className="space-y-3">
                            {correlations.slice(0, 5).map((c, i) => {
                                const meta = PATTERN_META[c.pattern || c.type] || { icon: '🔍', label: c.type, tactic: '—' };
                                const pal = SEVERITY_PALETTE[c.severity] || SEVERITY_PALETTE.low;
                                return (
                                    <div key={c.id || i} className={`flex items-center gap-3 p-3 rounded-lg border ${pal.bg} ${pal.border}`}>
                                        <span className="text-xl">{meta.icon}</span>
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2">
                                                <span className={`text-sm font-semibold ${pal.text}`}>{meta.label}</span>
                                                <span className="text-xs font-mono text-gray-400">{meta.tactic}</span>
                                            </div>
                                            <ConfidenceMeter value={c.confidence} />
                                        </div>
                                        <div className="text-right flex-shrink-0">
                                            <span className={`text-xs px-2 py-0.5 rounded-full font-medium uppercase ${pal.bg} ${pal.text}`}>{c.severity}</span>
                                            {c.auto_responded && <div className="text-xs text-green-500 mt-1">✓ auto-responded</div>}
                                        </div>
                                    </div>
                                );
                            })}
                            {correlations.length === 0 && !loading && (
                                <div className="text-center text-gray-400 py-8 text-sm">No correlations detected. Run analysis to scan events.</div>
                            )}
                        </div>
                    </div>

                    {/* XDR Intelligence Panel */}
                    <div className="bg-gradient-to-br from-cyan-900 to-blue-900 rounded-xl p-5 text-white">
                        <h2 className="text-base font-semibold mb-4">XDR Intelligence Engine</h2>
                        <div className="space-y-3 text-sm">
                            <div className="flex justify-between">
                                <span className="opacity-80">Correlation Patterns Loaded</span>
                                <span className="font-bold">5 MITRE ATT&CK</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="opacity-80">Detection Window</span>
                                <span className="font-bold">60 minutes rolling</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="opacity-80">Scan Interval</span>
                                <span className="font-bold text-green-400">Every 5 minutes</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="opacity-80">Auto-Playbook Trigger</span>
                                <span className="font-bold text-green-400">Enabled</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="opacity-80">Cross-Domain Sources</span>
                                <span className="font-bold">EDR + SIEM + Network</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="opacity-80">Avg Confidence Score</span>
                                <span className="font-bold">
                                    {correlations.length
                                        ? `${Math.round((correlations.reduce((s, c) => s + c.confidence, 0) / correlations.length) * 100)}%`
                                        : 'N/A'}
                                </span>
                            </div>
                        </div>
                    </div>

                    {/* Attack Pattern Coverage */}
                    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
                        <h2 className="text-base font-semibold text-gray-900 dark:text-white mb-4">Attack Pattern Coverage</h2>
                        <div className="space-y-2">
                            {Object.entries(PATTERN_META).map(([key, meta]) => {
                                const count = patternBreakdown[key] || 0;
                                return (
                                    <div key={key} className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                                        <span className="text-lg w-7 text-center">{meta.icon}</span>
                                        <div className="flex-1">
                                            <div className="text-sm font-medium text-gray-900 dark:text-white">{meta.label}</div>
                                            <div className="text-xs text-gray-400">{meta.tactic}</div>
                                        </div>
                                        <div className="text-right">
                                            <span className={`text-sm font-bold ${count > 0 ? 'text-red-500' : 'text-gray-400'}`}>{count}</span>
                                            <div className="text-xs text-gray-400">detections</div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                </div>
            )}

            {/* Correlations Tab */}
            {activeTab === 'correlations' && (
                <div className="space-y-4">
                    <div className="flex gap-2">
                        {(['all', 'critical', 'high', 'medium', 'low'] as const).map(s => (
                            <button key={s} onClick={() => setSeverityFilter(s)}
                                className={`px-3 py-1.5 text-xs font-medium rounded-lg capitalize transition-colors ${severityFilter === s ? 'bg-cyan-600 text-white' : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'}`}>
                                {s}
                            </button>
                        ))}
                    </div>

                    <div className="space-y-3">
                        {filtered.map((c, i) => {
                            const meta = PATTERN_META[c.pattern || c.type] || { icon: '🔍', label: c.type || 'Unknown', tactic: '—' };
                            const pal = SEVERITY_PALETTE[c.severity] || SEVERITY_PALETTE.low;
                            return (
                                <div key={c.id || i} className={`bg-white dark:bg-gray-800 rounded-xl border-l-4 p-5 shadow-sm ${c.severity === 'critical' ? 'border-red-500' : c.severity === 'high' ? 'border-orange-500' : c.severity === 'medium' ? 'border-yellow-500' : 'border-blue-500'}`}>
                                    <div className="flex items-start gap-4">
                                        <span className="text-3xl">{meta.icon}</span>
                                        <div className="flex-1">
                                            <div className="flex items-center gap-3 flex-wrap mb-2">
                                                <span className="text-base font-bold text-gray-900 dark:text-white">{meta.label}</span>
                                                <span className={`text-xs px-2.5 py-0.5 rounded-full font-bold uppercase ${pal.bg} ${pal.text}`}>{c.severity}</span>
                                                <span className="text-xs font-mono text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">{meta.tactic}</span>
                                                {c.auto_responded && (
                                                    <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 font-medium">
                                                        ✓ Auto-responded
                                                    </span>
                                                )}
                                            </div>

                                            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-3">
                                                <div>
                                                    <span className="text-xs text-gray-400">Events</span>
                                                    <div className="font-bold text-gray-900 dark:text-white">{c.event_count}</div>
                                                </div>
                                                <div>
                                                    <span className="text-xs text-gray-400">Window</span>
                                                    <div className="font-bold text-gray-900 dark:text-white">{c.time_window_minutes}m</div>
                                                </div>
                                                <div>
                                                    <span className="text-xs text-gray-400">Confidence</span>
                                                    <ConfidenceMeter value={c.confidence} />
                                                </div>
                                                <div>
                                                    <span className="text-xs text-gray-400">Detected</span>
                                                    <div className="font-medium text-gray-700 dark:text-gray-300 text-xs">{new Date(c.detected_at).toLocaleString()}</div>
                                                </div>
                                            </div>

                                            {c.description && (
                                                <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">{c.description}</p>
                                            )}

                                            {c.entities && c.entities.length > 0 && (
                                                <div className="flex flex-wrap gap-1">
                                                    <span className="text-xs text-gray-400">Entities:</span>
                                                    {c.entities.map((e, idx) => (
                                                        <span key={idx} className="text-xs px-1.5 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded font-mono">{e}</span>
                                                    ))}
                                                </div>
                                            )}

                                            {c.playbooks_triggered && c.playbooks_triggered.length > 0 && (
                                                <div className="mt-2 flex flex-wrap gap-1">
                                                    <span className="text-xs text-gray-400">Playbooks:</span>
                                                    {c.playbooks_triggered.map((pb, idx) => (
                                                        <span key={idx} className="text-xs px-1.5 py-0.5 bg-cyan-100 dark:bg-cyan-900/30 text-cyan-700 dark:text-cyan-300 rounded">{pb}</span>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                        {filtered.length === 0 && !loading && (
                            <div className="text-center text-gray-400 py-16">
                                <div className="text-4xl mb-3">🔍</div>
                                <div className="text-sm">No correlations found. Click <strong>Run Correlation Analysis</strong> to scan recent events.</div>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Automated Hunts Tab */}
            {activeTab === 'hunt' && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div className="grid grid-cols-2 gap-4">
                        {hunts ? [
                            { label: 'Findings (24h)', value: hunts.findingsLast24h, icon: '🎯', color: 'text-red-600' },
                            { label: 'Confirmed Threats', value: hunts.confirmedThreats, icon: '⚠️', color: 'text-orange-600' },
                            { label: 'Active Hunts', value: hunts.activeHunts, icon: '🔍', color: 'text-cyan-600' },
                            { label: 'False Positives', value: hunts.falsePositives, icon: '✅', color: 'text-green-600' },
                        ].map(item => (
                            <div key={item.label} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 text-center">
                                <div className="text-3xl mb-2">{item.icon}</div>
                                <div className={`text-3xl font-bold ${item.color}`}>{item.value}</div>
                                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">{item.label}</div>
                            </div>
                        )) : (
                            <div className="col-span-2 text-center text-gray-400 py-12">No hunt data available</div>
                        )}
                    </div>

                    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
                        <h2 className="text-base font-semibold text-gray-900 dark:text-white mb-4">Hunt Intelligence</h2>
                        <div className="space-y-4 text-sm">
                            <div className="p-3 bg-cyan-50 dark:bg-cyan-900/20 border border-cyan-200 dark:border-cyan-800 rounded-lg">
                                <div className="font-semibold text-cyan-700 dark:text-cyan-300 mb-1">Continuous Monitoring</div>
                                <p className="text-cyan-600 dark:text-cyan-400">XDR automated hunt runs every 5 minutes across all connected endpoints, correlating EDR telemetry, SIEM events, and network flows.</p>
                            </div>
                            <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                                <div className="font-semibold text-gray-700 dark:text-gray-300 mb-1">Detection Techniques</div>
                                <ul className="space-y-1 text-gray-600 dark:text-gray-400">
                                    <li>• MITRE ATT&CK pattern matching</li>
                                    <li>• Behavioral anomaly detection</li>
                                    <li>• Entity-based threat correlation</li>
                                    <li>• Time-series event clustering</li>
                                    <li>• IOC enrichment via threat intel</li>
                                </ul>
                            </div>
                            <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                                <div className="font-semibold text-gray-700 dark:text-gray-300 mb-1">Auto-Response Playbooks</div>
                                <ul className="space-y-1 text-gray-600 dark:text-gray-400">
                                    <li>• Isolate on lateral movement</li>
                                    <li>• Block IP on exfiltration</li>
                                    <li>• Alert SOC on credential access</li>
                                    <li>• Isolate on privilege escalation</li>
                                    <li>• Ransomware recovery (VSS)</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Attack Patterns Tab */}
            {activeTab === 'patterns' && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {Object.entries(PATTERN_META).map(([key, meta]) => {
                        const relCorrelations = correlations.filter(c => (c.pattern || c.type) === key);
                        const avgConfidence = relCorrelations.length
                            ? relCorrelations.reduce((s, c) => s + c.confidence, 0) / relCorrelations.length
                            : 0;
                        const detected = relCorrelations.length > 0;

                        return (
                            <div key={key} className={`bg-white dark:bg-gray-800 rounded-xl border-2 p-5 ${detected ? 'border-red-300 dark:border-red-700 shadow-md' : 'border-gray-200 dark:border-gray-700'}`}>
                                <div className="flex items-center gap-3 mb-3">
                                    <span className="text-3xl">{meta.icon}</span>
                                    <div>
                                        <div className="font-bold text-gray-900 dark:text-white text-sm">{meta.label}</div>
                                        <div className="text-xs font-mono text-gray-400">{meta.tactic}</div>
                                    </div>
                                    {detected && (
                                        <span className="ml-auto text-xs px-2 py-0.5 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-full font-bold">
                                            DETECTED
                                        </span>
                                    )}
                                </div>

                                <div className="space-y-2 text-sm">
                                    <div className="flex justify-between">
                                        <span className="text-gray-500 dark:text-gray-400">Detections</span>
                                        <span className={`font-bold ${relCorrelations.length > 0 ? 'text-red-600' : 'text-gray-400'}`}>{relCorrelations.length}</span>
                                    </div>
                                    {avgConfidence > 0 && (
                                        <div>
                                            <div className="flex justify-between mb-1">
                                                <span className="text-gray-500 dark:text-gray-400">Avg Confidence</span>
                                            </div>
                                            <ConfidenceMeter value={avgConfidence} />
                                        </div>
                                    )}
                                    <div className="flex justify-between">
                                        <span className="text-gray-500 dark:text-gray-400">Auto-responded</span>
                                        <span className="font-bold text-green-600">{relCorrelations.filter(c => c.auto_responded).length}</span>
                                    </div>
                                </div>

                                {relCorrelations.length > 0 && (
                                    <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400">
                                        Last: {new Date(relCorrelations[0].detected_at).toLocaleString()}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
};

export default XDRDashboard;
