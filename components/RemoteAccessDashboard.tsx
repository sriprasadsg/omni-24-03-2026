import React, { useState, useEffect, useCallback } from 'react';
import { Monitor, Terminal, RefreshCw, Wifi, WifiOff, ChevronRight, ShieldCheck, X, AlertTriangle, Loader, Users, Lock, Eye } from 'lucide-react';
import { RemoteDesktop } from './RemoteDesktop';
import { RemoteTerminal } from './RemoteTerminal';
import { Agent } from '../types';
import { authFetch, getRemoteCapabilities, disconnectRemoteSession } from '../services/apiService';

type AccessMode = 'desktop' | 'terminal';
type DesktopSubMode = 'view' | 'control';

interface RemoteCapabilities {
    can_view: boolean;
    can_control: boolean;
    error?: any;
}

export function RemoteAccessDashboard() {
    const [agents, setAgents] = useState<Agent[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
    const [mode, setMode] = useState<AccessMode>('terminal');
    const [desktopSubMode, setDesktopSubMode] = useState<DesktopSubMode>('view');
    const [capabilities, setCapabilities] = useState<RemoteCapabilities>({ can_view: false, can_control: false });
    const [capabilitiesLoading, setCapabilitiesLoading] = useState(true);
    const [showForceEndModal, setShowForceEndModal] = useState(false);
    const [forceEndTarget, setForceEndTarget] = useState<{ sessionId: string; hostname: string; tenantName: string; adminName: string; mode: string } | null>(null);

    const fetchAgents = useCallback(async (signal?: AbortSignal) => {
        setLoading(true);
        try {
            const res = await authFetch('/api/agents', { signal } as RequestInit);
            if (res.ok) {
                const data = await res.json();
                setAgents(Array.isArray(data) ? data : data.items || data.agents || []);
            }
        } catch (e) {
            if ((e as any)?.name !== 'AbortError') console.error('Failed to load remote agents:', e);
        }
        setLoading(false);
    }, []);

    const fetchCapabilities = useCallback(async (signal?: AbortSignal) => {
        setCapabilitiesLoading(true);
        try {
            const res = await authFetch('/api/remote/capabilities', { signal } as RequestInit);
            if (res.ok) {
                const data = await res.json();
                setCapabilities({ can_view: !!data.can_view, can_control: !!data.can_control });
            } else {
                setCapabilities({ can_view: false, can_control: false });
            }
        } catch (e) {
            console.error('Failed to fetch remote capabilities:', e);
            setCapabilities({ can_view: false, can_control: false });
        }
        setCapabilitiesLoading(false);
    }, []);

    useEffect(() => {
        const controller = new AbortController();
        fetchAgents(controller.signal);
        return () => controller.abort();
    }, [fetchAgents]);

    useEffect(() => {
        if (selectedAgent && mode === 'desktop') {
            const controller = new AbortController();
            fetchCapabilities(controller.signal);
            return () => controller.abort();
        }
    }, [selectedAgent, mode, fetchCapabilities]);

    const onlineAgents = agents.filter(a =>
        ['Online', 'online', 'Active', 'active'].includes(a.status)
    );

    const handleForceEnd = async () => {
        if (!forceEndTarget) return;
        try {
            await disconnectRemoteSession(forceEndTarget.sessionId);
        } catch (e) {
            console.error('Force end failed:', e);
        }
        setShowForceEndModal(false);
        setForceEndTarget(null);
    };

    if (selectedAgent) {
        if (mode === 'desktop') {
            const isPlatformAdmin = capabilities.can_control;
            return (
                <div className="flex flex-col h-full bg-slate-950">
                    <div className="flex items-center justify-between p-4 border-b border-slate-800 bg-slate-900/50">
                        <div className="flex items-center gap-3 truncate max-w-[70%]">
                            <button
                                onClick={() => setSelectedAgent(null)}
                                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-400 bg-slate-800/50 border border-slate-700 rounded-lg hover:bg-slate-800 hover:text-slate-200 transition-colors"
                            >
                                <ChevronRight className="size-4 rotate-180" />
                                Back
                            </button>
                            <Monitor className="size-5 text-emerald-400" />
                            <div className="flex flex-col truncate">
                                <span className="text-sm font-semibold text-slate-100 truncate">Remote Desktop — {selectedAgent.hostname || selectedAgent.id}</span>
                                <span className="text-xs text-slate-500 truncate">{selectedAgent.ipAddress || 'No IP'} · {selectedAgent.platform || 'Unknown platform'}</span>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            {capabilitiesLoading && <Loader className="size-4 text-slate-500 animate-spin" />}
                            {!capabilitiesLoading && capabilities.can_control && (
                                <div className="flex items-center gap-1 bg-slate-800/50 border border-slate-700 rounded-lg p-1">
                                    <button
                                        onClick={() => setDesktopSubMode('view')}
                                        className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                                            desktopSubMode === 'view'
                                                ? 'bg-blue-600 text-white'
                                                : 'text-slate-400 hover:text-slate-200'
                                        }`}
                                    >
                                        <Eye className="size-3.5 mr-1" />
                                        View
                                    </button>
                                    <button
                                        onClick={() => setDesktopSubMode('control')}
                                        className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                                            desktopSubMode === 'control'
                                                ? 'bg-emerald-600 text-white'
                                                : 'text-slate-400 hover:text-slate-200'
                                        }`}
                                    >
                                        <ShieldCheck className="size-3.5 mr-1" />
                                        Control
                                    </button>
                                </div>
                            )}
                            {!capabilitiesLoading && !capabilities.can_control && desktopSubMode !== 'view' && (
                                <span className="text-xs text-slate-500">Control unavailable</span>
                            )}
                        </div>
                    </div>
                    <div className="flex-1 overflow-hidden">
                        <RemoteDesktop
                            agentId={selectedAgent.id}
                            mode={desktopSubMode}
                            hostname={selectedAgent.hostname}
                        />
                    </div>

                    {/* Force End Session Modal */}
                    {showForceEndModal && forceEndTarget && (
                        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
                            <div className="bg-slate-900 border border-red-500/50 rounded-xl shadow-2xl max-w-md w-full">
                                <div className="p-6">
                                    <div className="flex items-center gap-3 mb-4">
                                        <div className="w-10 h-10 rounded-full bg-red-500/20 flex items-center justify-center">
                                            <AlertTriangle className="size-5 text-red-400" />
                                        </div>
                                        <h3 className="text-slate-100 font-semibold text-lg">Force End Session</h3>
                                    </div>
                                    <div className="space-y-3 mb-6 text-sm text-slate-400">
                                        <p>You are about to terminate an active remote control session across tenant boundaries.</p>
                                        <div className="bg-slate-800/50 rounded-lg p-3 space-y-1.5">
                                            <div className="flex justify-between">
                                                <span>Admin</span>
                                                <span className="text-slate-200 font-mono">{forceEndTarget.adminName}</span>
                                            </div>
                                            <div className="flex justify-between">
                                                <span>Mode</span>
                                                <span className="text-slate-200 font-medium capitalize">{forceEndTarget.mode}</span>
                                            </div>
                                            <div className="flex justify-between">
                                                <span>Hostname</span>
                                                <span className="text-slate-200 font-mono truncate max-w-[160px]">{forceEndTarget.hostname}</span>
                                            </div>
                                            <div className="flex justify-between">
                                                <span>Tenant</span>
                                                <span className="text-slate-200 font-mono">{forceEndTarget.tenantName}</span>
                                            </div>
                                        </div>
                                        <p className="text-red-400">This action cannot be undone. The endpoint user will be disconnected immediately.</p>
                                    </div>
                                    <div className="flex justify-end gap-3">
                                        <button
                                            onClick={() => { setShowForceEndModal(false); setForceEndTarget(null); }}
                                            className="px-4 py-2 text-xs font-medium text-slate-300 bg-slate-800 border border-slate-700 rounded-lg hover:bg-slate-700 transition-colors"
                                        >
                                            Cancel
                                        </button>
                                        <button
                                            onClick={handleForceEnd}
                                            className="px-4 py-2 text-xs font-semibold text-white bg-red-600 border border-red-500 rounded-lg hover:bg-red-700 transition-colors"
                                        >
                                            Force End Session
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            );
        }
        return (
            <div className="flex flex-col h-full bg-slate-950">
                <div className="flex items-center gap-3 p-4 border-b border-slate-800 bg-slate-900/50">
                    <button
                        onClick={() => setSelectedAgent(null)}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-400 bg-slate-800/50 border border-slate-700 rounded-lg hover:bg-slate-800 hover:text-slate-200 transition-colors"
                    >
                        <ChevronRight className="size-4 rotate-180" />
                        Back
                    </button>
                    <Terminal className="size-5 text-emerald-400" />
                    <div className="flex flex-col truncate">
                        <span className="text-sm font-semibold text-slate-100 truncate">Remote Terminal — {selectedAgent.hostname || selectedAgent.id}</span>
                        <span className="text-xs text-slate-500 truncate">{selectedAgent.ipAddress || 'No IP'} · {selectedAgent.platform || 'Unknown platform'}</span>
                    </div>
                </div>
                <div className="flex-1 overflow-hidden">
                    <RemoteTerminal agent={selectedAgent} onClose={() => setSelectedAgent(null)} />
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-slate-950 p-6 text-slate-100 font-sans">
            <div className="mb-8">
                <div className="text-xs font-bold uppercase tracking-wider text-blue-500 mb-2">AGENTS</div>
                <h1 className="text-3xl font-bold tracking-tight mb-2">Remote Access</h1>
                <p className="text-slate-400 text-sm">Connect to agents via Remote Desktop or Terminal</p>
            </div>

            <div className="flex flex-wrap items-center gap-4 mb-8">
                <div className="flex bg-slate-900/50 border border-slate-800 rounded-lg p-1">
                    {(['terminal', 'desktop'] as AccessMode[]).map(m => (
                        <button
                            key={m}
                            onClick={() => setMode(m)}
                            className={`flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-md transition-colors ${
                                mode === m
                                    ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                                    : 'text-slate-400 hover:text-slate-200'
                            }`}
                        >
                            {m === 'terminal' ? <Terminal className="size-4" /> : <Monitor className="size-4" />}
                            {m === 'terminal' ? 'Terminal' : 'Desktop'}
                        </button>
                    ))}
                </div>
                <button
                    onClick={() => { void fetchAgents(); }}
                    className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-blue-400 bg-blue-500/10 border border-blue-500/30 rounded-lg hover:bg-blue-500/20 transition-colors"
                >
                    <RefreshCw className="size-4" />
                    Refresh
                </button>
            </div>

            {loading ? (
                <div className="text-center text-slate-400 py-16">Loading agents…</div>
            ) : agents.length === 0 ? (
                <div className="text-center py-16 text-slate-400">
                    <WifiOff className="size-10 mx-auto mb-4 opacity-40" />
                    <div className="font-semibold mb-2">No agents registered</div>
                    <div className="text-sm">Deploy an agent and it will appear here once it connects.</div>
                </div>
            ) : (
                <>
                    {onlineAgents.length === 0 && agents.length > 0 && (
                        <div className="mb-6 p-4 bg-amber-500/10 border border-amber-500/30 rounded-lg text-amber-400 text-sm flex items-center gap-3">
                            <WifiOff className="size-5" />
                            {agents.length} agent{agents.length !== 1 ? 's' : ''} registered but none are currently online. Remote access requires an online agent.
                        </div>
                    )}
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                        {agents.map(agent => {
                            const isOnline = ['Online', 'online', 'Active', 'active'].includes(agent.status);
                            return (
                                <div
                                    key={agent.id}
                                    onClick={() => isOnline && setSelectedAgent(agent)}
                                    className={`group flex items-center justify-between p-5 rounded-xl transition-all cursor-pointer ${
                                        isOnline
                                            ? 'bg-slate-900/50 border border-slate-800 hover:border-blue-500/40'
                                            : 'bg-slate-900/30 border border-slate-800/50 opacity-50 cursor-not-allowed'
                                    }`}
                                >
                                    <div className="flex items-center gap-4">
                                        <div className={`size-12 rounded-lg flex items-center justify-center ${isOnline ? 'bg-emerald-500/10' : 'bg-slate-700/10'}`}>
                                            {isOnline ? <Wifi className="size-6 text-emerald-400" /> : <WifiOff className="size-6 text-slate-500" />}
                                        </div>
                                        <div className="truncate max-w-[200px]">
                                            <div className="flex items-center gap-2 font-semibold text-base">
                                                <span className="truncate">{agent.hostname || agent.id}</span>
                                                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${isOnline ? 'bg-emerald-500/15 text-emerald-400' : 'bg-slate-700/15 text-slate-500'}`}>
                                                    {agent.status || 'Unknown'}
                                                </span>
                                            </div>
                                            <div className="text-xs text-slate-500 mt-1 truncate">
                                                {agent.ipAddress || 'No IP'} · {agent.platform || 'Unknown platform'}
                                            </div>
                                        </div>
                                    </div>
                                    {isOnline && <ChevronRight className="size-5 text-slate-500 group-hover:text-slate-300 transition-colors" />}
                                </div>
                            );
                        })}
                    </div>
                </>
            )}
        </div>
    );
}

export default RemoteAccessDashboard;