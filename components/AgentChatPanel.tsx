/**
 * AgentChatPanel — Admin portal side of admin-to-endpoint chat.
 *
 * Admin selects an online agent/asset, types a message, and the agent on that
 * machine pops up a GUI window on the endpoint's physical desktop. Replies from
 * the endpoint user are pushed back via Socket.IO in real time.
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Monitor, MessageSquare, Send, X, RefreshCw, Wifi, WifiOff, Clock, AlertTriangle, ArrowUpCircle, UserCheck } from 'lucide-react';
import { authFetch } from '../services/apiService';
import { socketService } from '../services/socketService';
import { Agent } from '../types';
import { useUser } from '../contexts/UserContext';

// ── Types ─────────────────────────────────────────────────────────────────────

interface ChatMessage {
    id: string;
    sender_type: 'admin' | 'user' | 'system';
    sender_id: string;
    sender_role?: string;
    sender_name?: string;
    content: string;
    created_at: string;
}

interface PlatformAdmin {
    username: string;
    name: string;
    email: string;
    role: string;
    online: boolean;
}

interface ChatSession {
    id: string;
    agent_id: string;
    agent_hostname: string;
    subject: string;
    status: 'active' | 'closed';
    initiator_id: string;
    initiator_type?: 'admin' | 'endpoint';
    escalated?: boolean;
    escalated_at?: string;
    escalated_by?: string;
    escalation_note?: string;
    messages?: ChatMessage[];
    message_count?: number;
    last_message?: ChatMessage;
    created_at: string;
    updated_at: string;
}

// ── API helpers ───────────────────────────────────────────────────────────────

const API = '/api/agent-chat';

async function apiPost<T>(url: string, body: object): Promise<T> {
    const r = await authFetch(url, { method: 'POST', body: JSON.stringify(body) });
    if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail ?? 'Request failed'); }
    return r.json();
}

async function apiGet<T>(url: string): Promise<T> {
    const r = await authFetch(url);
    if (!r.ok) throw new Error('Request failed');
    return r.json();
}

// ── Start chat modal ──────────────────────────────────────────────────────────

const StartChatModal: React.FC<{
    agent: Agent;
    onClose: () => void;
    onStarted: (s: ChatSession) => void;
}> = ({ agent, onClose, onStarted }) => {
    const [subject, setSubject]   = useState('');
    const [message, setMessage]   = useState('');
    const [sending, setSending]   = useState(false);
    const [err, setErr]           = useState('');

    const submit = async () => {
        if (!subject.trim() || !message.trim()) { setErr('Subject and message are required'); return; }
        setSending(true);
        try {
            const session = await apiPost<ChatSession>(`${API}/sessions`, {
                agent_id: agent.id, subject, message,
            });
            onStarted(session);
            onClose();
        } catch (e: any) {
            setErr(e.message ?? 'Failed to start chat');
        } finally { setSending(false); }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
            <div className="bg-slate-900 border border-slate-700 rounded-2xl p-6 w-full max-w-lg shadow-2xl">
                <div className="flex items-center gap-3 mb-5">
                    <div className="w-10 h-10 rounded-xl bg-indigo-600/20 flex items-center justify-center">
                        <Monitor size={20} className="text-indigo-400" />
                    </div>
                    <div>
                        <h2 className="text-white font-semibold text-base">Chat with Endpoint</h2>
                        <p className="text-slate-400 text-xs mt-0.5">
                            A popup will appear on <span className="text-indigo-300 font-medium">{agent.hostname}</span> ({agent.ipAddress})
                        </p>
                    </div>
                </div>

                {err && <p className="text-red-400 text-xs mb-3 bg-red-900/20 px-3 py-2 rounded-lg">{err}</p>}

                <div className="space-y-3">
                    <div>
                        <label className="text-slate-400 text-xs block mb-1">Subject *</label>
                        <input
                            autoFocus
                            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
                            placeholder="e.g. Scheduled maintenance tonight at 10pm"
                            value={subject} onChange={e => setSubject(e.target.value)}
                        />
                    </div>
                    <div>
                        <label className="text-slate-400 text-xs block mb-1">Initial message *</label>
                        <textarea
                            rows={4}
                            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 resize-none"
                            placeholder="This message will appear on the user's screen immediately…"
                            value={message} onChange={e => setMessage(e.target.value)}
                        />
                    </div>
                </div>

                <div className="flex justify-end gap-3 mt-5">
                    <button onClick={onClose} className="px-4 py-2 text-slate-400 text-sm hover:text-white">Cancel</button>
                    <button
                        onClick={submit} disabled={sending}
                        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-lg disabled:opacity-50 flex items-center gap-2"
                    >
                        <MessageSquare size={14} />
                        {sending ? 'Opening chat…' : 'Send to endpoint'}
                    </button>
                </div>
            </div>
        </div>
    );
};

// ── Message bubble ────────────────────────────────────────────────────────────

const Bubble: React.FC<{ msg: ChatMessage; myUsername: string }> = ({ msg, myUsername }) => {
    const timeStr = new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    // ── System / escalation notice — centred amber strip ─────────────────────
    if (msg.sender_type === 'system' || msg.sender_id === 'system') {
        return (
            <div className="flex justify-center mb-4">
                <div className="bg-amber-900/25 border border-amber-700/30 rounded-xl px-4 py-2 text-xs text-amber-300 max-w-[90%] text-center">
                    {msg.content}
                    <span className="text-amber-400/50 ml-2">{timeStr}</span>
                </div>
            </div>
        );
    }

    const isEndpointUser = msg.sender_type === 'user';
    const isMine         = !isEndpointUser && msg.sender_id === myUsername;

    // Resolve display name and role from message fields (set by backend)
    const displayName = msg.sender_name || msg.sender_id;
    const role        = msg.sender_role || (isEndpointUser ? 'Endpoint User' : 'Admin');

    // Colour coding by role:
    //   endpoint user  → left, slate
    //   me (any admin) → right, indigo
    //   tenant admin   → left, teal
    //   platform/super admin → left, purple
    const isSuperAdmin = !isEndpointUser && !isMine &&
        ['Super Admin', 'super_admin', 'admin', 'platform-admin'].includes(role);
    const isTenantAdmin = !isEndpointUser && !isMine && !isSuperAdmin;

    const bubbleCls = isMine
        ? 'bg-indigo-600 text-white rounded-br-sm'
        : isSuperAdmin
            ? 'bg-purple-800/60 text-white rounded-bl-sm'
            : isEndpointUser
                ? 'bg-slate-700 text-slate-100 rounded-bl-sm'
                : 'bg-teal-800/60 text-white rounded-bl-sm';   // tenant admin

    const labelCls = isMine
        ? 'text-indigo-200'
        : isSuperAdmin
            ? 'text-purple-300'
            : isEndpointUser
                ? 'text-teal-400'
                : 'text-teal-200';

    // Label: always shown on every message so all parties know who is talking
    const label = isEndpointUser
        ? `🖥 ${displayName}`
        : isMine
            ? `You · ${displayName}`
            : `${role} · ${displayName}`;

    return (
        <div className={`flex ${isMine ? 'justify-end' : 'justify-start'} mb-3`}>
            <div className={`max-w-[72%] rounded-2xl px-4 py-2.5 text-sm ${bubbleCls}`}>
                <p className={`text-[10px] font-semibold mb-1 ${labelCls}`}>{label}</p>
                <p className="whitespace-pre-wrap break-words">{msg.content}</p>
                <p className={`text-[10px] mt-1 opacity-60`}>{timeStr}</p>
            </div>
        </div>
    );
};

// ── Session list item ─────────────────────────────────────────────────────────

const SessionItem: React.FC<{
    session: ChatSession;
    active: boolean;
    onClick: () => void;
}> = ({ session, active, onClick }) => (
    <button
        onClick={onClick}
        className={`w-full text-left px-4 py-3 border-b border-slate-800 hover:bg-slate-800/50 transition-colors ${active ? 'bg-slate-800' : ''}`}
    >
        <div className="flex items-start justify-between gap-2 mb-1">
            <span className="text-sm font-medium text-white truncate flex-1">{session.agent_hostname}</span>
            <div className="flex gap-1 flex-shrink-0">
                {session.escalated && (
                    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/30">
                        ↑ Escalated
                    </span>
                )}
                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${
                    session.status === 'active'
                        ? 'bg-green-500/20 text-green-400 border-green-500/30'
                        : 'bg-slate-500/20 text-slate-400 border-slate-500/30'
                }`}>{session.status}</span>
            </div>
        </div>
        <div className="flex items-center gap-1.5 mb-0.5">
            {session.initiator_type === 'endpoint' && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-teal-900/40 text-teal-300">
                    🖥 Endpoint initiated
                </span>
            )}
            <p className="text-xs text-slate-400 truncate">{session.subject}</p>
        </div>
        <p className="text-[11px] text-slate-500 truncate">{session.last_message?.content ?? 'No messages'}</p>
        <p className="text-[10px] text-slate-600 mt-1">{new Date(session.updated_at).toLocaleString()}</p>
    </button>
);

// ── Escalate modal ────────────────────────────────────────────────────────────

const EscalateModal: React.FC<{
    session: ChatSession;
    onClose: () => void;
    onEscalated: (s: ChatSession) => void;
}> = ({ session, onClose, onEscalated }) => {
    const [note, setNote]                   = useState('');
    const [saving, setSaving]               = useState(false);
    const [err, setErr]                     = useState('');
    const [admins, setAdmins]               = useState<PlatformAdmin[]>([]);
    const [loadingAdmins, setLoadingAdmins] = useState(true);
    const [selectedAdmin, setSelectedAdmin] = useState<string>(''); // '' = notify all

    useEffect(() => {
        apiGet<PlatformAdmin[]>(`${API}/platform-admins`)
            .then(d => { setAdmins(Array.isArray(d) ? d : []); setLoadingAdmins(false); })
            .catch(() => setLoadingAdmins(false));
    }, []);

    const submit = async () => {
        setSaving(true);
        try {
            const updated = await apiPost<ChatSession>(
                `${API}/sessions/${session.id}/escalate`,
                { note, target_admin: selectedAdmin || undefined }
            );
            onEscalated(updated);
            onClose();
        } catch (e: any) { setErr(e.message ?? 'Failed to escalate'); }
        finally { setSaving(false); }
    };

    const onlineCount = admins.filter(a => a.online).length;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
            <div className="bg-slate-900 border border-slate-700 rounded-2xl p-6 w-full max-w-md shadow-2xl">
                <div className="flex items-center gap-3 mb-4">
                    <div className="w-9 h-9 rounded-xl bg-amber-600/20 flex items-center justify-center">
                        <ArrowUpCircle size={18} className="text-amber-400" />
                    </div>
                    <div>
                        <h2 className="text-white font-semibold text-base">Escalate to Platform Admin</h2>
                        <p className="text-slate-400 text-xs mt-0.5">
                            {onlineCount > 0
                                ? <><span className="text-green-400 font-medium">{onlineCount} online</span> · {admins.length} total</>
                                : `${admins.length} platform admin${admins.length !== 1 ? 's' : ''} available`}
                        </p>
                    </div>
                </div>

                {/* Issue context */}
                <div className="mb-4 px-3 py-2.5 bg-amber-900/20 border border-amber-700/40 rounded-lg text-xs space-y-0.5">
                    <p className="text-amber-300 font-semibold">Issue being escalated</p>
                    <p className="text-slate-300">Host: <span className="text-white font-medium">{session.agent_hostname}</span></p>
                    <p className="text-slate-300">Subject: <span className="text-white">{session.subject}</span></p>
                </div>

                {/* Admin picker */}
                <p className="text-slate-400 text-xs mb-2">Notify <span className="text-white">who?</span></p>
                <div className="space-y-1 max-h-40 overflow-y-auto mb-4">
                    {/* Notify all option */}
                    <button
                        onClick={() => setSelectedAdmin('')}
                        className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left text-sm transition-colors ${
                            selectedAdmin === '' ? 'bg-amber-600/20 border border-amber-600/40' : 'hover:bg-slate-800'
                        }`}
                    >
                        <div className="w-7 h-7 rounded-full bg-amber-600/30 flex items-center justify-center text-amber-300 flex-shrink-0">
                            <AlertTriangle size={13} />
                        </div>
                        <div>
                            <p className="text-white text-xs font-medium">All Platform Admins</p>
                            <p className="text-slate-400 text-[10px]">Broadcast to all — fastest response</p>
                        </div>
                        {selectedAdmin === '' && <UserCheck size={13} className="text-amber-400 ml-auto" />}
                    </button>

                    {loadingAdmins && <p className="text-slate-500 text-xs px-3 py-2">Loading admins…</p>}
                    {admins.map(a => (
                        <button key={a.username}
                            onClick={() => setSelectedAdmin(a.username)}
                            className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors ${
                                selectedAdmin === a.username ? 'bg-purple-600/20 border border-purple-600/40' : 'hover:bg-slate-800'
                            }`}
                        >
                            <div className="relative flex-shrink-0">
                                <div className="w-7 h-7 rounded-full bg-purple-600/30 flex items-center justify-center text-purple-200 text-xs font-bold">
                                    {(a.name[0] ?? '?').toUpperCase()}
                                </div>
                                <span className={`absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full border border-slate-900 ${a.online ? 'bg-green-400' : 'bg-slate-500'}`} />
                            </div>
                            <div className="min-w-0 flex-1">
                                <p className="text-white text-xs font-medium truncate">{a.name}</p>
                                <p className="text-slate-400 text-[10px] truncate">{a.email} · {a.role}</p>
                            </div>
                            {selectedAdmin === a.username && <UserCheck size={13} className="text-purple-400 flex-shrink-0" />}
                        </button>
                    ))}
                </div>

                {err && <p className="text-red-400 text-xs mb-3 bg-red-900/20 px-3 py-2 rounded-lg">{err}</p>}
                <label className="text-slate-400 text-xs block mb-1">Note for Platform Admin (optional)</label>
                <textarea
                    rows={2} autoFocus
                    className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500 resize-none"
                    placeholder="Describe what you've tried and why this needs escalation…"
                    value={note} onChange={e => setNote(e.target.value)}
                />
                <div className="flex justify-end gap-3 mt-4">
                    <button onClick={onClose} className="px-4 py-2 text-slate-400 text-sm hover:text-white">Cancel</button>
                    <button onClick={submit} disabled={saving}
                        className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white text-sm rounded-lg disabled:opacity-50 flex items-center gap-2">
                        <ArrowUpCircle size={14} />
                        {saving ? 'Escalating…' : selectedAdmin ? `Escalate to ${admins.find(a => a.username === selectedAdmin)?.name ?? selectedAdmin}` : 'Escalate to All'}
                    </button>
                </div>
            </div>
        </div>
    );
};

// ── Main panel ────────────────────────────────────────────────────────────────

interface AgentChatPanelProps {
    /** If provided, pre-selects this agent for a new chat on open */
    initialAgent?: Agent | null;
    onClose?: () => void;
}

const AgentChatPanel: React.FC<AgentChatPanelProps> = ({ initialAgent, onClose }) => {
    const { currentUser }                   = useUser();
    const myUsername                        = (currentUser as any)?.email ?? (currentUser as any)?.username ?? '';

    const [agents, setAgents]               = useState<Agent[]>([]);
    const [sessions, setSessions]           = useState<ChatSession[]>([]);
    const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
    const [activeId, setActiveId]           = useState<string | null>(null);
    const [input, setInput]                 = useState('');
    const [sending, setSending]             = useState(false);
    const [loadingSessions, setLoadingSessions] = useState(true);
    const [startFor, setStartFor]           = useState<Agent | null>(initialAgent ?? null);
    const [showAgentPicker, setShowAgentPicker] = useState(false);
    const [escalateFor, setEscalateFor]     = useState<ChatSession | null>(null);
    const bottomRef = useRef<HTMLDivElement>(null);

    // ── Load agents + sessions ────────────────────────────────────────────────
    const loadSessions = useCallback(async () => {
        setLoadingSessions(true);
        try {
            const data = await apiGet<ChatSession[]>(`${API}/sessions`);
            setSessions(Array.isArray(data) ? data : []);
        } finally { setLoadingSessions(false); }
    }, []);

    useEffect(() => {
        authFetch('/api/agents?limit=100')
            .then(r => r.json())
            .then(d => setAgents(Array.isArray(d) ? d : d.items ?? d.agents ?? []))
            .catch(() => {});
        loadSessions();
    }, [loadSessions]);

    // Open start-chat modal immediately if an agent was passed in
    useEffect(() => { if (initialAgent) setStartFor(initialAgent); }, [initialAgent]);

    // ── Load active session ───────────────────────────────────────────────────
    useEffect(() => {
        if (!activeId) { setActiveSession(null); return; }
        apiGet<ChatSession>(`${API}/sessions/${activeId}`).then(setActiveSession).catch(() => {});
    }, [activeId]);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [activeSession?.messages?.length]);

    // ── Polling fallback every 3 s ────────────────────────────────────────────
    useEffect(() => {
        if (!activeId) return;
        const id = setInterval(async () => {
            try {
                const fresh = await apiGet<ChatSession>(`${API}/sessions/${activeId}`);
                setActiveSession(prev => {
                    if (!prev) return fresh;
                    if ((fresh.messages ?? []).length === (prev.messages ?? []).length) return prev;
                    return fresh;
                });
            } catch { /* ignore */ }
        }, 3000);
        return () => clearInterval(id);
    }, [activeId]);

    // ── Real-time via Socket.IO ───────────────────────────────────────────────
    useEffect(() => {
        const handler = (data: any) => {
            if (data.event === 'agent_chat_message') {
                if (data.session_id === activeId) {
                    setActiveSession(prev => {
                        if (!prev) return prev;
                        const exists = (prev.messages ?? []).some(m => m.id === data.message.id);
                        if (exists) return prev;
                        return { ...prev, messages: [...(prev.messages ?? []), data.message] };
                    });
                }
                setSessions(prev => prev.map(s =>
                    s.id === data.session_id
                        ? { ...s, last_message: data.message, updated_at: data.message.created_at }
                        : s
                ));
            }
            if (data.event === 'agent_chat_initiated') {
                // New endpoint-initiated session arrived — reload list
                loadSessions();
            }
            if (data.event === 'agent_chat_escalated') {
                setSessions(prev => prev.map(s =>
                    s.id === data.session_id ? { ...s, escalated: true } : s
                ));
                if (data.session_id === activeId) {
                    setActiveSession(prev => prev ? { ...prev, escalated: true, messages: [...(prev.messages ?? []), data.message] } : prev);
                }
            }
        };
        socketService.on('agent_chat', handler);
        return () => socketService.off('agent_chat', handler);
    }, [activeId]);

    // ── Send admin message ────────────────────────────────────────────────────
    const handleSend = async () => {
        if (!activeId || !input.trim() || sending) return;
        if (activeSession?.status === 'closed') return;
        const content = input.trim();
        setInput('');
        setSending(true);
        try {
            const msg = await apiPost<ChatMessage>(
                `${API}/sessions/${activeId}/admin-message`, { content }
            );
            setActiveSession(prev => prev ? { ...prev, messages: [...(prev.messages ?? []), msg] } : prev);
        } catch { setInput(content); }
        finally { setSending(false); }
    };

    const handleClose = async () => {
        if (!activeId) return;
        await authFetch(`${API}/sessions/${activeId}/close`, { method: 'PATCH' }).catch(() => {});
        setActiveSession(prev => prev ? { ...prev, status: 'closed' } : prev);
        setSessions(prev => prev.map(s => s.id === activeId ? { ...s, status: 'closed' } : s));
    };

    const onlineAgents = agents.filter(a => ['Online', 'online', 'Active', 'active'].includes(a.status));

    return (
        <div className="flex h-full bg-slate-950 text-white overflow-hidden">

            {/* ── Left: session list ──────────────────────────────────────── */}
            <div className="w-72 flex-shrink-0 border-r border-slate-800 flex flex-col">
                <div className="p-4 border-b border-slate-800">
                    <div className="flex items-center justify-between mb-3">
                        <h2 className="font-semibold text-sm flex items-center gap-2">
                            <Monitor size={15} className="text-indigo-400" />
                            Endpoint Chats
                        </h2>
                        <div className="flex gap-2">
                            <button onClick={() => setShowAgentPicker(true)}
                                className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1 rounded-lg">
                                + New
                            </button>
                            <button onClick={loadSessions}
                                className="text-slate-400 hover:text-white p-1 rounded" title="Refresh">
                                <RefreshCw size={13} />
                            </button>
                        </div>
                    </div>
                    <p className="text-[11px] text-slate-500">
                        Messages are delivered as popups on the endpoint's physical screen.
                    </p>
                </div>

                <div className="flex-1 overflow-y-auto">
                    {loadingSessions && <p className="text-slate-500 text-sm p-4">Loading…</p>}
                    {!loadingSessions && sessions.length === 0 && (
                        <div className="p-6 text-center">
                            <Monitor size={32} className="mx-auto text-slate-700 mb-2" />
                            <p className="text-slate-500 text-sm">No chats yet</p>
                            <button onClick={() => setShowAgentPicker(true)}
                                className="mt-2 text-indigo-400 text-xs hover:underline">
                                Start one →
                            </button>
                        </div>
                    )}
                    {sessions.map(s => (
                        <SessionItem key={s.id} session={s}
                            active={activeId === s.id}
                            onClick={() => setActiveId(s.id)} />
                    ))}
                </div>
            </div>

            {/* ── Right: message thread ───────────────────────────────────── */}
            <div className="flex-1 flex flex-col">
                {!activeSession ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-slate-500 gap-3">
                        <Monitor size={48} className="text-slate-700" />
                        <p className="text-sm">Select a session or start a new endpoint chat</p>
                        <button onClick={() => setShowAgentPicker(true)}
                            className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg mt-1">
                            + Chat with an Asset
                        </button>
                    </div>
                ) : (
                    <>
                        {/* Header */}
                        <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
                            <div>
                                <div className="flex items-center gap-2 flex-wrap">
                                    <Monitor size={14} className="text-indigo-400" />
                                    <h3 className="font-semibold text-sm">{activeSession.agent_hostname}</h3>
                                    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${
                                        activeSession.status === 'active'
                                            ? 'bg-green-500/20 text-green-400 border-green-500/30'
                                            : 'bg-slate-500/20 text-slate-400 border-slate-500/30'
                                    }`}>{activeSession.status}</span>
                                    {activeSession.initiator_type === 'endpoint' && (
                                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-teal-900/40 text-teal-300">🖥 Endpoint initiated</span>
                                    )}
                                    {activeSession.escalated && (
                                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/40 text-amber-300">↑ Escalated to Platform Admin</span>
                                    )}
                                </div>
                                <p className="text-xs text-slate-400 mt-0.5">{activeSession.subject}</p>
                            </div>
                            <div className="flex items-center gap-2">
                                {activeSession.status === 'active' && !activeSession.escalated && (
                                    <button onClick={() => setEscalateFor(activeSession)}
                                        className="text-xs bg-amber-700/40 hover:bg-amber-600 text-amber-300 hover:text-white px-3 py-1 rounded-lg transition-colors flex items-center gap-1">
                                        <ArrowUpCircle size={12} /> Escalate
                                    </button>
                                )}
                                {activeSession.status === 'active' && (
                                    <button onClick={handleClose}
                                        className="text-xs bg-red-700/40 hover:bg-red-700 text-red-300 hover:text-white px-3 py-1 rounded-lg transition-colors">
                                        End Chat
                                    </button>
                                )}
                                {onClose && (
                                    <button onClick={onClose} className="text-slate-400 hover:text-white p-1">
                                        <X size={16} />
                                    </button>
                                )}
                            </div>
                        </div>

                        {/* Escalation context banner */}
                        {activeSession.escalated && (
                            <div className="px-5 py-2 bg-amber-950/40 border-b border-amber-700/30 flex items-center gap-2 flex-wrap text-xs text-amber-300">
                                <AlertTriangle size={11} className="flex-shrink-0" />
                                <span>Escalated by <span className="font-medium text-white">{activeSession.escalated_by}</span></span>
                                {(activeSession as any).escalation_target ? (
                                    <span>→ <span className="font-medium text-purple-300">{(activeSession as any).escalation_target}</span></span>
                                ) : (
                                    <span className="text-amber-200/60">→ All Platform Admins</span>
                                )}
                                {activeSession.escalation_note && (
                                    <span className="text-amber-200/70 truncate">— {activeSession.escalation_note}</span>
                                )}
                            </div>
                        )}

                        {/* Info banner */}
                        {!activeSession.escalated && (
                            <div className="px-5 py-2 bg-indigo-950/40 border-b border-indigo-900/30 flex items-center gap-2 text-xs text-indigo-300">
                                <Wifi size={11} />
                                {activeSession.initiator_type === 'endpoint'
                                    ? 'Endpoint user has requested assistance. Reply here to respond.'
                                    : 'A chat window is open on the endpoint\'s physical screen. Replies appear here in real time.'}
                            </div>
                        )}

                        {/* Messages */}
                        <div className="flex-1 overflow-y-auto px-5 py-4">
                            {(activeSession.messages ?? []).length === 0 && (
                                <div className="flex items-center gap-2 text-slate-500 text-xs py-4">
                                    <Clock size={13} />
                                    Waiting for the endpoint to connect…
                                </div>
                            )}
                            {(activeSession.messages ?? []).map(msg => (
                                <Bubble key={msg.id} msg={msg} myUsername={myUsername} />
                            ))}
                            <div ref={bottomRef} />
                        </div>

                        {/* Input */}
                        {activeSession.status === 'closed' ? (
                            <div className="px-5 py-3 border-t border-slate-800 text-center text-xs text-slate-500">
                                This chat session has ended.
                            </div>
                        ) : (
                            <div className="px-5 py-3 border-t border-slate-800 flex items-end gap-3 bg-slate-900/30">
                                <textarea
                                    rows={2}
                                    value={input}
                                    onChange={e => setInput(e.target.value)}
                                    onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                                    placeholder="Type a message to the endpoint user… (Enter to send)"
                                    className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 resize-none"
                                />
                                <button
                                    onClick={handleSend}
                                    disabled={sending || !input.trim()}
                                    className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-xl disabled:opacity-40 flex-shrink-0 flex items-center gap-2"
                                >
                                    <Send size={14} />
                                    {sending ? '…' : 'Send'}
                                </button>
                            </div>
                        )}
                    </>
                )}
            </div>

            {/* ── Agent picker modal ──────────────────────────────────────── */}
            {showAgentPicker && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
                    <div className="bg-slate-900 border border-slate-700 rounded-2xl p-5 w-full max-w-md shadow-2xl">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-white font-semibold text-base">Select Online Asset</h2>
                            <button onClick={() => setShowAgentPicker(false)} className="text-slate-400 hover:text-white">×</button>
                        </div>
                        {onlineAgents.length === 0 ? (
                            <div className="text-center py-8">
                                <WifiOff size={32} className="mx-auto text-slate-600 mb-2" />
                                <p className="text-slate-500 text-sm">No online agents available</p>
                            </div>
                        ) : (
                            <div className="max-h-72 overflow-y-auto space-y-2">
                                {onlineAgents.map(a => (
                                    <button key={a.id} onClick={() => { setStartFor(a); setShowAgentPicker(false); }}
                                        className="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-slate-800 transition-colors text-left">
                                        <div className="w-9 h-9 rounded-lg bg-green-600/20 flex items-center justify-center flex-shrink-0">
                                            <Monitor size={16} className="text-green-400" />
                                        </div>
                                        <div className="min-w-0">
                                            <p className="text-white text-sm font-medium truncate">{a.hostname}</p>
                                            <p className="text-slate-400 text-xs truncate">{a.ipAddress} · {a.platform}</p>
                                        </div>
                                        <Wifi size={14} className="text-green-400 flex-shrink-0 ml-auto" />
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* ── Compose modal ───────────────────────────────────────────── */}
            {startFor && (
                <StartChatModal
                    agent={startFor}
                    onClose={() => setStartFor(null)}
                    onStarted={session => {
                        setSessions(prev => [session, ...prev]);
                        setActiveId(session.id);
                    }}
                />
            )}

            {/* ── Escalate modal ──────────────────────────────────────────── */}
            {escalateFor && (
                <EscalateModal
                    session={escalateFor}
                    onClose={() => setEscalateFor(null)}
                    onEscalated={updated => {
                        setSessions(prev => prev.map(s => s.id === updated.id ? { ...s, escalated: true } : s));
                        setActiveSession(updated);
                        setEscalateFor(null);
                    }}
                />
            )}
        </div>
    );
};

export default AgentChatPanel;
