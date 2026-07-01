import React, { useState, useEffect, useCallback } from 'react';
import {
    fetchSecurityIntelStatus,
    saveSecurityIntelConfig,
    testSecurityIntelProvider,
    syncSecurityIntelProvider,
    pushSecurityIntelToAgents,
} from '../services/apiService';
import { showToast } from '../utils/toast';

// ── Types ─────────────────────────────────────────────────────────────────────

interface Connector {
    provider:       string;
    name:           string;
    category:       string;
    description:    string;
    status:         'connected' | 'unconfigured' | 'configured' | 'error';
    message:        string;
    configured:     boolean;
    api_key_hint:   string | null;
    configured_at:  string | null;
    record_count:   number | null;
    last_sync:      string | null;
    docs_url:       string;
    free_tier:      string;
    requires_key:   boolean;
    key_env_var:    string | null;
}

interface IntelStatus {
    connectors:   Connector[];
    total:        number;
    connected:    number;
    unconfigured: number;
    errors:       number;
}

// ── Provider icons (inline SVG) ───────────────────────────────────────────────

const VTIcon = () => (
    <svg viewBox="0 0 32 32" className="w-7 h-7" fill="none">
        <rect width="32" height="32" rx="8" fill="#394EFF"/>
        <path d="M7 8l9 16 9-16H7z" fill="white" fillOpacity="0.9"/>
        <path d="M16 8l-5 9h10L16 8z" fill="white"/>
    </svg>
);

const NVDIcon = () => (
    <svg viewBox="0 0 32 32" className="w-7 h-7" fill="none">
        <rect width="32" height="32" rx="8" fill="#003087"/>
        <text x="16" y="22" textAnchor="middle" fontSize="11" fontWeight="bold" fill="white" fontFamily="monospace">NVD</text>
    </svg>
);

const OSVIcon = () => (
    <svg viewBox="0 0 32 32" className="w-7 h-7" fill="none">
        <rect width="32" height="32" rx="8" fill="#0F9D58"/>
        <path d="M16 6c-5.523 0-10 4.477-10 10s4.477 10 10 10 10-4.477 10-10S21.523 6 16 6zm0 3a7 7 0 110 14A7 7 0 0116 9zm-1 3v5l4 2.5-.75 1.23-4.75-3V12h1.5z" fill="white"/>
    </svg>
);

const EPSSIcon = () => (
    <svg viewBox="0 0 32 32" className="w-7 h-7" fill="none">
        <rect width="32" height="32" rx="8" fill="#D4380D"/>
        <path d="M8 22l6-12 4 8 3-5 3 4" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
);

const PROVIDER_ICONS: Record<string, React.ReactNode> = {
    virustotal: <VTIcon />,
    nvd:        <NVDIcon />,
    osv:        <OSVIcon />,
    epss:       <EPSSIcon />,
};

// ── Status helpers ────────────────────────────────────────────────────────────

const STATUS_CONFIG = {
    connected:    { dot: '#10b981', label: 'Connected',    bg: 'rgba(16,185,129,0.12)',  border: 'rgba(16,185,129,0.25)',  text: '#34d399' },
    unconfigured: { dot: '#64748b', label: 'Not set up',   bg: 'rgba(100,116,139,0.10)', border: 'rgba(100,116,139,0.2)',  text: '#94a3b8' },
    configured:   { dot: '#f59e0b', label: 'Key saved',    bg: 'rgba(245,158,11,0.10)',  border: 'rgba(245,158,11,0.25)',  text: '#fbbf24' },
    error:        { dot: '#ef4444', label: 'Error',         bg: 'rgba(239,68,68,0.10)',   border: 'rgba(239,68,68,0.25)',   text: '#f87171' },
} as const;

function StatusBadge({ status }: { status: Connector['status'] }) {
    const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.unconfigured;
    return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold"
            style={{ background: cfg.bg, border: `1px solid ${cfg.border}`, color: cfg.text }}>
            <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: cfg.dot, boxShadow: `0 0 4px ${cfg.dot}` }} />
            {cfg.label}
        </span>
    );
}

function fmt(n: number | null | undefined): string {
    if (n == null) return '—';
    return n.toLocaleString();
}
function fmtDate(s: string | null | undefined): string {
    if (!s) return 'Never';
    try { return new Date(s).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }); }
    catch { return s; }
}

// ── Config modal ──────────────────────────────────────────────────────────────

interface ConfigModalProps {
    connector: Connector;
    onClose:   () => void;
    onSaved:   () => void;
}

const ConfigModal: React.FC<ConfigModalProps> = ({ connector, onClose, onSaved }) => {
    const [key, setKey]   = useState('');
    const [saving, setSaving] = useState(false);

    const handleSave = async () => {
        setSaving(true);
        try {
            await saveSecurityIntelConfig(connector.provider, key);
            showToast(`${connector.name} API key saved`, 'success');
            onSaved();
            onClose();
        } catch (e: any) {
            showToast(e.message || 'Failed to save', 'error');
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}>
            <div className="w-full max-w-md rounded-2xl p-6 slide-up" style={{
                background: 'rgba(12,12,32,0.96)',
                border: '1px solid rgba(255,255,255,0.1)',
                boxShadow: '0 24px 80px rgba(0,0,0,0.6)',
            }}>
                <div className="flex items-center gap-3 mb-6">
                    {PROVIDER_ICONS[connector.provider]}
                    <div>
                        <h3 className="text-lg font-bold text-white">Configure {connector.name}</h3>
                        <p className="text-xs text-slate-400">{connector.category}</p>
                    </div>
                </div>

                {connector.api_key_hint && (
                    <div className="mb-4 flex items-center gap-2 px-3 py-2 rounded-lg text-sm" style={{ background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)' }}>
                        <span className="text-emerald-400">✓</span>
                        <span className="text-slate-300">Current key: <code className="font-mono text-emerald-400">{connector.api_key_hint}</code></span>
                    </div>
                )}

                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                    {connector.key_env_var ?? 'API Key'}
                </label>
                <input
                    type="password"
                    value={key}
                    onChange={e => setKey(e.target.value)}
                    placeholder={connector.api_key_hint ? 'Enter new key to replace…' : 'Paste your API key here'}
                    className="w-full px-4 py-3 rounded-xl text-sm text-white placeholder-slate-500 outline-none mb-2"
                    style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)' }}
                    onFocus={e => { e.currentTarget.style.border = '1px solid rgba(0,210,255,0.4)'; e.currentTarget.style.boxShadow = '0 0 0 3px rgba(0,210,255,0.1)'; }}
                    onBlur={e => { e.currentTarget.style.border = '1px solid rgba(255,255,255,0.12)'; e.currentTarget.style.boxShadow = 'none'; }}
                    autoFocus
                />
                <p className="text-[11px] text-slate-500 mb-1">
                    Free tier: <span className="text-slate-400">{connector.free_tier}</span>
                </p>
                <a href={connector.docs_url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-primary-400 hover:underline">
                    Get API key →
                </a>

                <div className="flex gap-3 mt-6">
                    <button
                        onClick={handleSave}
                        disabled={saving || key.length < 8}
                        className="flex-1 py-2.5 rounded-xl text-sm font-semibold text-white transition-all disabled:opacity-40"
                        style={{ background: 'linear-gradient(135deg, #00d2ff, #3a7bd5)' }}
                    >
                        {saving ? 'Saving…' : 'Save API Key'}
                    </button>
                    <button
                        onClick={onClose}
                        className="px-4 py-2.5 rounded-xl text-sm font-medium text-slate-400 transition-all hover:text-white"
                        style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)' }}
                    >
                        Cancel
                    </button>
                </div>
            </div>
        </div>
    );
};

// ── Connector card ────────────────────────────────────────────────────────────

interface CardProps {
    connector:  Connector;
    onRefresh:  () => void;
}

const ConnectorCard: React.FC<CardProps> = ({ connector, onRefresh }) => {
    const [testing,  setTesting]  = useState(false);
    const [syncing,  setSyncing]  = useState(false);
    const [testResult, setTestResult] = useState<{ success: boolean; message: string; detail?: string } | null>(null);
    const [configOpen, setConfigOpen] = useState(false);

    const handleTest = async () => {
        setTesting(true);
        setTestResult(null);
        try {
            const res = await testSecurityIntelProvider(connector.provider);
            setTestResult(res);
            if (res.success) onRefresh();
        } catch {
            setTestResult({ success: false, message: 'Request failed' });
        } finally {
            setTesting(false);
        }
    };

    const handleSync = async () => {
        setSyncing(true);
        try {
            const res = await syncSecurityIntelProvider(connector.provider);
            showToast(res.message || 'Sync started', res.success ? 'success' : 'error');
            if (res.success) setTimeout(onRefresh, 3000);
        } catch {
            showToast('Sync failed', 'error');
        } finally {
            setSyncing(false);
        }
    };

    const canSync   = ['nvd', 'osv'].includes(connector.provider);
    const canConfig = connector.requires_key || connector.key_env_var != null;

    return (
        <>
            {configOpen && (
                <ConfigModal
                    connector={connector}
                    onClose={() => setConfigOpen(false)}
                    onSaved={onRefresh}
                />
            )}

            <div className="glass rounded-2xl p-5 flex flex-col gap-4 slide-up" style={{ transition: 'box-shadow 0.2s' }}>
                {/* Header */}
                <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                        <div className="flex-shrink-0">{PROVIDER_ICONS[connector.provider]}</div>
                        <div>
                            <h3 className="text-base font-bold text-white leading-tight">{connector.name}</h3>
                            <p className="text-[11px] text-slate-500 font-medium tracking-wide uppercase mt-0.5">{connector.category}</p>
                        </div>
                    </div>
                    <StatusBadge status={connector.status} />
                </div>

                {/* Description */}
                <p className="text-sm text-slate-400 leading-relaxed">{connector.description}</p>

                {/* Stats row */}
                <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-xl px-3 py-2.5" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)' }}>
                        <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Records Synced</p>
                        <p className="text-lg font-bold text-white">{fmt(connector.record_count)}</p>
                    </div>
                    <div className="rounded-xl px-3 py-2.5" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)' }}>
                        <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Last Sync</p>
                        <p className="text-xs font-medium text-slate-300 mt-1">{fmtDate(connector.last_sync)}</p>
                    </div>
                </div>

                {/* API key info */}
                {connector.api_key_hint && (
                    <div className="flex items-center gap-2 px-3 py-2 rounded-lg" style={{ background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.18)' }}>
                        <span className="text-emerald-400 text-xs">🔑</span>
                        <span className="text-xs text-slate-300">Key: <code className="font-mono text-emerald-400">{connector.api_key_hint}</code></span>
                        {connector.configured_at && (
                            <span className="ml-auto text-[10px] text-slate-500">{fmtDate(connector.configured_at)}</span>
                        )}
                    </div>
                )}

                {!connector.api_key_hint && connector.requires_key && (
                    <div className="flex items-center gap-2 px-3 py-2 rounded-lg" style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)' }}>
                        <span className="text-amber-400 text-xs">⚠</span>
                        <span className="text-xs text-amber-300">API key required — {connector.free_tier}</span>
                        <a href={connector.docs_url} target="_blank" rel="noopener noreferrer"
                            className="ml-auto text-[10px] text-primary-400 hover:underline flex-shrink-0">
                            Get key →
                        </a>
                    </div>
                )}

                {/* Test result */}
                {testResult && (
                    <div className="px-3 py-2 rounded-lg text-xs" style={{
                        background: testResult.success ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                        border: `1px solid ${testResult.success ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'}`,
                        color: testResult.success ? '#34d399' : '#f87171',
                    }}>
                        <p className="font-medium">{testResult.success ? '✓' : '✗'} {testResult.message}</p>
                        {testResult.detail && <p className="mt-0.5 opacity-80">{testResult.detail}</p>}
                    </div>
                )}

                {/* Actions */}
                <div className="flex gap-2 pt-1">
                    <button
                        onClick={handleTest}
                        disabled={testing}
                        className="flex-1 py-2 rounded-xl text-xs font-semibold text-slate-200 transition-all disabled:opacity-40 hover:text-white"
                        style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)' }}
                    >
                        {testing ? '⏳ Testing…' : '⚡ Test Connection'}
                    </button>

                    {canSync && (
                        <button
                            onClick={handleSync}
                            disabled={syncing}
                            className="flex-1 py-2 rounded-xl text-xs font-semibold text-slate-200 transition-all disabled:opacity-40 hover:text-white"
                            style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)' }}
                        >
                            {syncing ? '⏳ Starting…' : '🔄 Sync Now'}
                        </button>
                    )}

                    {canConfig && (
                        <button
                            onClick={() => setConfigOpen(true)}
                            className="px-4 py-2 rounded-xl text-xs font-semibold transition-all hover:brightness-110"
                            style={{ background: 'linear-gradient(135deg, rgba(0,210,255,0.2), rgba(127,0,255,0.2))', border: '1px solid rgba(0,210,255,0.3)', color: '#7dd3fc' }}
                        >
                            ⚙ Configure
                        </button>
                    )}
                </div>

                {/* Docs link */}
                <a href={connector.docs_url} target="_blank" rel="noopener noreferrer"
                    className="text-[11px] text-slate-600 hover:text-primary-400 transition-colors text-center">
                    {connector.docs_url.replace('https://', '')} ↗
                </a>
            </div>
        </>
    );
};

// ── Summary bar ───────────────────────────────────────────────────────────────

const SummaryBar: React.FC<{ data: IntelStatus; loading: boolean; onRefresh: () => void }> = ({ data, loading, onRefresh }) => (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
            <h1 className="text-2xl font-bold tracking-tight text-gradient">Security Intelligence Connectors</h1>
            <p className="text-sm text-slate-500 mt-1">Live connectivity status for threat intel and vulnerability data sources</p>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
            {/* Mini stats */}
            <div className="flex items-center gap-4 px-4 py-2 rounded-xl" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
                <span className="text-sm"><span className="font-bold text-emerald-400">{data.connected}</span><span className="text-slate-500 ml-1 text-xs">connected</span></span>
                <span className="text-slate-700">|</span>
                <span className="text-sm"><span className="font-bold text-amber-400">{data.unconfigured}</span><span className="text-slate-500 ml-1 text-xs">pending</span></span>
                {data.errors > 0 && <>
                    <span className="text-slate-700">|</span>
                    <span className="text-sm"><span className="font-bold text-red-400">{data.errors}</span><span className="text-slate-500 ml-1 text-xs">errors</span></span>
                </>}
            </div>
            <button
                onClick={onRefresh}
                disabled={loading}
                className="p-2.5 rounded-xl text-slate-400 hover:text-white transition-all"
                style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.08)' }}
                title="Refresh status"
            >
                <svg className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M23 4v6h-6M1 20v-6h6" strokeLinecap="round" strokeLinejoin="round"/>
                    <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
            </button>
        </div>
    </div>
);

// ── Agent distribution panel ──────────────────────────────────────────────────

const AgentDistributionPanel: React.FC<{ vtConnected: boolean }> = ({ vtConnected }) => {
    const [pushing,    setPushing]    = useState(false);
    const [pushResult, setPushResult] = useState<{ success: boolean; message: string; agents_updated?: number; pushed_at?: string } | null>(null);

    const handlePush = async () => {
        setPushing(true);
        setPushResult(null);
        try {
            const res = await pushSecurityIntelToAgents();
            setPushResult(res);
            showToast(res.message, res.success ? 'success' : 'error');
        } catch (e: any) {
            setPushResult({ success: false, message: e.message || 'Push failed' });
            showToast(e.message || 'Push failed', 'error');
        } finally {
            setPushing(false);
        }
    };

    return (
        <div className="rounded-2xl p-6" style={{ background: 'rgba(127,0,255,0.06)', border: '1px solid rgba(127,0,255,0.18)' }}>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="flex items-start gap-4">
                    {/* Icon */}
                    <div className="flex-shrink-0 w-11 h-11 rounded-xl flex items-center justify-center text-xl"
                        style={{ background: 'linear-gradient(135deg, rgba(127,0,255,0.3), rgba(0,210,255,0.2))', border: '1px solid rgba(127,0,255,0.4)' }}>
                        📡
                    </div>
                    <div>
                        <h3 className="text-base font-bold text-white">Push to Agents</h3>
                        <p className="text-sm text-slate-400 mt-0.5 max-w-xl">
                            Distribute the VirusTotal API key to all registered agents so they can perform direct IOC lookups from the endpoint — without needing the key set as a local environment variable on each machine.
                        </p>
                        <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs text-slate-400">
                            <div className="flex items-start gap-2">
                                <span className="text-emerald-400 mt-0.5">✓</span>
                                <span>Key stored in agent's <code className="font-mono text-slate-300">capabilityConfig</code> in MongoDB</span>
                            </div>
                            <div className="flex items-start gap-2">
                                <span className="text-emerald-400 mt-0.5">✓</span>
                                <span>Agent picks it up automatically on next config refresh (every poll cycle)</span>
                            </div>
                            <div className="flex items-start gap-2">
                                <span className="text-emerald-400 mt-0.5">✓</span>
                                <span>Works for both online and offline agents (offline ones get it on reconnect)</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="flex-shrink-0">
                    <button
                        onClick={handlePush}
                        disabled={pushing || !vtConnected}
                        className="px-6 py-3 rounded-xl text-sm font-semibold text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
                        style={{
                            background: vtConnected ? 'linear-gradient(135deg, #7f00ff, #3a7bd5)' : undefined,
                            boxShadow: vtConnected ? '0 4px 20px rgba(127,0,255,0.3)' : undefined,
                        }}
                        title={!vtConnected ? 'VirusTotal must be connected before pushing' : undefined}
                    >
                        {pushing ? '⏳ Pushing…' : '📡 Push to All Agents'}
                    </button>
                    {!vtConnected && (
                        <p className="text-[11px] text-amber-400 mt-1.5 text-center">VirusTotal must be connected first</p>
                    )}
                </div>
            </div>

            {/* Push result */}
            {pushResult && (
                <div className="mt-4 flex items-start gap-3 px-4 py-3 rounded-xl" style={{
                    background: pushResult.success ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                    border: `1px solid ${pushResult.success ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'}`,
                }}>
                    <span className="text-lg">{pushResult.success ? '✅' : '❌'}</span>
                    <div>
                        <p className="text-sm font-medium" style={{ color: pushResult.success ? '#34d399' : '#f87171' }}>
                            {pushResult.message}
                        </p>
                        {pushResult.success && pushResult.agents_updated != null && (
                            <p className="text-xs text-slate-500 mt-0.5">
                                {pushResult.agents_updated} agent(s) updated · pushed at {fmtDate(pushResult.pushed_at)}
                            </p>
                        )}
                        {pushResult.success && (
                            <p className="text-xs text-slate-500 mt-1">
                                Agents will apply the new key on their next configuration poll (typically within 5 minutes).
                            </p>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

// ── Main page ─────────────────────────────────────────────────────────────────

export const SecurityIntelConnectors: React.FC = () => {
    const [data,    setData]    = useState<IntelStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [error,   setError]   = useState<string | null>(null);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await fetchSecurityIntelStatus();
            setData(res);
        } catch (e: any) {
            setError(e.message || 'Failed to load status');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center py-20 gap-4">
                <div className="w-12 h-12 rounded-2xl flex items-center justify-center text-2xl" style={{ background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)' }}>⚠</div>
                <p className="text-slate-400 text-sm">{error}</p>
                <button onClick={load} className="px-4 py-2 rounded-xl text-sm text-white" style={{ background: 'linear-gradient(135deg, #00d2ff, #3a7bd5)' }}>
                    Retry
                </button>
            </div>
        );
    }

    const empty: IntelStatus = { connectors: [], total: 0, connected: 0, unconfigured: 0, errors: 0 };
    const info = data ?? empty;

    return (
        <div className="space-y-6 pb-8 fade-in">
            <SummaryBar data={info} loading={loading} onRefresh={load} />

            {/* Connector grid */}
            {loading && !data ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5">
                    {[...Array(4)].map((_, i) => (
                        <div key={i} className="glass rounded-2xl h-64 shimmer" />
                    ))}
                </div>
            ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5">
                    {info.connectors.map(c => (
                        <ConnectorCard key={c.provider} connector={c} onRefresh={load} />
                    ))}
                </div>
            )}

            {/* Agent distribution */}
            <AgentDistributionPanel vtConnected={info.connectors.find(c => c.provider === 'virustotal')?.status === 'connected'} />

            {/* Info panel */}
            <div className="rounded-2xl p-5" style={{ background: 'rgba(0,210,255,0.04)', border: '1px solid rgba(0,210,255,0.12)' }}>
                <h3 className="text-sm font-semibold text-primary-400 mb-3">About these integrations</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs text-slate-400 leading-relaxed">
                    <div>
                        <p className="font-medium text-slate-300 mb-1">VirusTotal & EPSS</p>
                        <p>Used by Threat Intelligence scanning (Threat Intel → Scan Artifact) and security event enrichment to automatically flag malicious IPs, domains, and file hashes detected by your agents.</p>
                    </div>
                    <div>
                        <p className="font-medium text-slate-300 mb-1">NVD & OSV</p>
                        <p>Feed the Patch Management and Vulnerability Management dashboards with real CVE data. The NVD sync runs every 24h automatically; OSV covers open-source package vulnerabilities across 20+ ecosystems.</p>
                    </div>
                </div>
            </div>
        </div>
    );
};
