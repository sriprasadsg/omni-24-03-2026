import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
    fetchSupportConversations, startSupportConversation,
    fetchSupportConversation, sendSupportMessage, updateSupportStatus,
    fetchTenantUsersForChat, markSupportConversationRead, fetchSupportPresence,
} from '../services/apiService';
import { socketService } from '../services/socketService';
import { webrtcCallService } from '../services/webrtcCallService';
import { SupportConversation, SupportMessage, TenantUser } from '../types';
import { useUser } from '../contexts/UserContext';

// ── Role helpers ──────────────────────────────────────────────────────────────

const SUPER_ROLES  = new Set(['Super Admin', 'super_admin', 'admin', 'platform-admin']);
const ADMIN_ROLES  = new Set(['Tenant Admin', 'tenant_admin', ...SUPER_ROLES]);
const isSuper = (r?: string) => SUPER_ROLES.has(r ?? '');
const isAdmin = (r?: string) => ADMIN_ROLES.has(r ?? '');

// ── Status badge ──────────────────────────────────────────────────────────────

const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
    const map: Record<string, string> = {
        open:        'bg-blue-500/20 text-blue-400 border-blue-500/30',
        in_progress: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
        resolved:    'bg-green-500/20 text-green-400 border-green-500/30',
        closed:      'bg-slate-500/20 text-slate-400 border-slate-500/30',
    };
    return (
        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${map[status] ?? map.open}`}>
            {status.replace('_', ' ')}
        </span>
    );
};

const ChatTypePill: React.FC<{ type: string }> = ({ type }) => {
    const cfg: Record<string, { label: string; cls: string }> = {
        user_to_admin:       { label: 'Support',   cls: 'bg-teal-900/40 text-teal-300' },
        admin_to_superadmin: { label: 'Escalated', cls: 'bg-purple-900/40 text-purple-300' },
        admin_to_user:       { label: 'Direct',    cls: 'bg-indigo-900/40 text-indigo-300' },
    };
    const { label, cls } = cfg[type] ?? cfg.user_to_admin;
    return <span className={`px-1.5 py-0.5 rounded text-[10px] ${cls}`}>{label}</span>;
};

// ── New conversation modal (shared) ──────────────────────────────────────────

const NewConvoModal: React.FC<{
    chatType: 'user_to_admin' | 'admin_to_superadmin' | 'admin_to_user';
    targetUser?: TenantUser | null;
    originalConvo?: SupportConversation | null;
    onClose: () => void;
    onCreate: (c: SupportConversation) => void;
}> = ({ chatType, targetUser, originalConvo, onClose, onCreate }) => {
    const defaultSubject = originalConvo ? `Escalation: ${originalConvo.subject}` : '';
    const [subject, setSubject]   = useState(defaultSubject);
    const [message, setMessage]   = useState('');
    const [saving, setSaving]     = useState(false);
    const [err, setErr]           = useState('');

    const labels: Record<string, string> = {
        admin_to_superadmin: originalConvo ? 'Escalate Conversation to Super Admin' : 'Escalate to Super Admin',
        admin_to_user:       `Message ${targetUser?.name ?? 'User'}`,
        user_to_admin:       'Contact Support',
    };

    const submit = async () => {
        if (!subject.trim() || !message.trim()) { setErr('Subject and message are required'); return; }
        setSaving(true);
        try {
            const payload: Parameters<typeof startSupportConversation>[0] = {
                subject, message, chat_type: chatType,
            };
            if (chatType === 'admin_to_user' && targetUser) {
                payload.target_user_id   = targetUser.id;
                payload.target_user_name = targetUser.name;
            }
            if (chatType === 'admin_to_superadmin' && originalConvo) {
                payload.original_convo_id   = originalConvo.id;
                payload.original_subject    = originalConvo.subject;
                payload.original_user_name  = originalConvo.initiator_name ?? originalConvo.initiator_id;
                payload.original_user_email = originalConvo.initiator_email ?? originalConvo.initiator_id;
            }
            const c = await startSupportConversation(payload);
            onCreate(c);
            onClose();
        } catch { setErr('Failed to start conversation'); }
        finally { setSaving(false); }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <div className="bg-slate-900 border border-slate-700 rounded-2xl p-6 w-full max-w-lg shadow-2xl">
                <h2 className="text-white font-semibold text-lg mb-1">{labels[chatType]}</h2>
                {chatType === 'admin_to_user' && targetUser && (
                    <p className="text-slate-400 text-xs mb-4">To: <span className="text-indigo-300">{targetUser.name}</span> ({targetUser.email})</p>
                )}
                {chatType === 'admin_to_superadmin' && originalConvo && (
                    <div className="mb-4 px-3 py-2.5 bg-purple-900/25 border border-purple-700/40 rounded-lg text-xs">
                        <p className="text-purple-300 font-semibold mb-1">Escalating user conversation</p>
                        <p className="text-slate-300">User: <span className="text-white font-medium">{originalConvo.initiator_name ?? originalConvo.initiator_id}</span>
                            {originalConvo.initiator_email && <span className="text-slate-400"> · {originalConvo.initiator_email}</span>}
                        </p>
                        <p className="text-slate-300 mt-0.5">Issue: <span className="text-white">{originalConvo.subject}</span></p>
                    </div>
                )}
                {err && <p className="text-red-400 text-xs mb-3">{err}</p>}
                <div className="space-y-3">
                    <div>
                        <label className="text-slate-400 text-xs block mb-1">Subject *</label>
                        <input
                            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-teal-500"
                            placeholder="Brief description"
                            value={subject} onChange={e => setSubject(e.target.value)}
                        />
                    </div>
                    <div>
                        <label className="text-slate-400 text-xs block mb-1">Message *</label>
                        <textarea
                            rows={4}
                            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-teal-500 resize-none"
                            placeholder="Your message…"
                            value={message} onChange={e => setMessage(e.target.value)}
                        />
                    </div>
                </div>
                <div className="flex justify-end gap-3 mt-5">
                    <button onClick={onClose} className="px-4 py-2 text-slate-400 text-sm hover:text-white">Cancel</button>
                    <button
                        onClick={submit} disabled={saving}
                        className="px-4 py-2 bg-teal-600 hover:bg-teal-500 text-white text-sm rounded-lg disabled:opacity-50"
                    >{saving ? 'Sending…' : 'Send'}</button>
                </div>
            </div>
        </div>
    );
};

// ── User picker modal (admin → user) ─────────────────────────────────────────

const UserPickerModal: React.FC<{
    onSelect: (u: TenantUser) => void;
    onClose: () => void;
}> = ({ onSelect, onClose }) => {
    const [users, setUsers]     = useState<TenantUser[]>([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch]   = useState('');

    useEffect(() => {
        fetchTenantUsersForChat().then(d => { setUsers(Array.isArray(d) ? d : []); setLoading(false); });
    }, []);

    const filtered = users.filter(u =>
        u.name.toLowerCase().includes(search.toLowerCase()) ||
        u.email.toLowerCase().includes(search.toLowerCase())
    );

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <div className="bg-slate-900 border border-slate-700 rounded-2xl p-5 w-full max-w-md shadow-2xl">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-white font-semibold text-base">Select User to Message</h2>
                    <button onClick={onClose} className="text-slate-400 hover:text-white text-xl leading-none">×</button>
                </div>
                <input
                    autoFocus
                    className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm mb-3 focus:outline-none focus:border-indigo-500"
                    placeholder="Search by name or email…"
                    value={search} onChange={e => setSearch(e.target.value)}
                />
                <div className="max-h-72 overflow-y-auto space-y-1">
                    {loading && <p className="text-slate-400 text-sm text-center py-4">Loading users…</p>}
                    {!loading && filtered.length === 0 && (
                        <p className="text-slate-500 text-sm text-center py-4">No users found</p>
                    )}
                    {filtered.map(u => (
                        <button
                            key={u.id}
                            onClick={() => onSelect(u)}
                            className="w-full text-left flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-slate-800 transition-colors"
                        >
                            <div className="w-8 h-8 rounded-full bg-indigo-600/30 flex items-center justify-center text-indigo-300 font-semibold text-sm flex-shrink-0">
                                {(u.name || u.email)[0]?.toUpperCase() ?? '?'}
                            </div>
                            <div className="min-w-0">
                                <p className="text-white text-sm font-medium truncate">{u.name || u.email}</p>
                                <p className="text-slate-400 text-xs truncate">{u.email} · {u.role}</p>
                            </div>
                        </button>
                    ))}
                </div>
            </div>
        </div>
    );
};

// ── Message bubble ────────────────────────────────────────────────────────────

const Bubble: React.FC<{ msg: SupportMessage; isMine: boolean }> = ({ msg, isMine }) => (
    <div className={`flex ${isMine ? 'justify-end' : 'justify-start'} mb-3`}>
        <div className={`max-w-[72%] rounded-2xl px-4 py-2.5 text-sm ${
            isMine
                ? 'bg-teal-600 text-white rounded-br-sm'
                : 'bg-slate-700 text-slate-100 rounded-bl-sm'
        }`}>
            {!isMine && (
                <p className="text-[10px] font-semibold text-teal-400 mb-1 capitalize">
                    {msg.sender_role.replace('_', ' ')}
                </p>
            )}
            <p className="whitespace-pre-wrap break-words">{msg.content}</p>
            <p className={`text-[10px] mt-1 ${isMine ? 'text-teal-200' : 'text-slate-400'}`}>
                {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </p>
        </div>
    </div>
);

// ── User identity card (shown to admins in the chat header) ──────────────────

const UserIdentityCard: React.FC<{ convo: SupportConversation; isOnline?: boolean }> = ({ convo, isOnline }) => {
    const name  = convo.initiator_name  ?? convo.initiator_id;
    const email = convo.initiator_email ?? convo.initiator_id;
    const role  = convo.initiator_role  ?? 'user';
    const initial = (name[0] ?? '?').toUpperCase();

    return (
        <div className="flex items-center gap-2.5 px-3 py-1.5 bg-teal-900/20 border border-teal-700/30 rounded-xl">
            <div className="relative flex-shrink-0">
                <div className="w-7 h-7 rounded-full bg-teal-600/40 flex items-center justify-center text-teal-200 font-bold text-xs">
                    {initial}
                </div>
                {isOnline !== undefined && (
                    <span className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-slate-900
                        ${isOnline ? 'bg-green-400' : 'bg-slate-500'}`} />
                )}
            </div>
            <div className="min-w-0">
                <p className="text-teal-100 text-xs font-semibold leading-tight truncate">{name}</p>
                <p className="text-teal-300/70 text-[10px] leading-tight truncate">{email} · {role}</p>
            </div>
        </div>
    );
};

// ── Main component ────────────────────────────────────────────────────────────

interface SupportChatPanelProps {
    /** Conversation to auto-open (deep-link from a toast / notification). */
    initialConvoId?: string | null;
    /** Fired once the deep-linked conversation has been opened. */
    onConvoConsumed?: () => void;
}

const SupportChatPanel: React.FC<SupportChatPanelProps> = ({ initialConvoId = null, onConvoConsumed }) => {
    const { currentUser } = useUser();
    const role   = (currentUser as any)?.role ?? 'user';
    const myId   = (currentUser as any)?.email ?? (currentUser as any)?.username ?? '';

    const [convos, setConvos]                   = useState<SupportConversation[]>([]);
    const [activeId, setActiveId]               = useState<string | null>(null);
    const [activeConvo, setActiveConvo]         = useState<SupportConversation | null>(null);
    const [input, setInput]                     = useState('');
    const [sending, setSending]                 = useState(false);
    const [loading, setLoading]                 = useState(true);
    const [filter, setFilter]                   = useState<'all' | 'open' | 'resolved'>('all');

    // Modal state
    const [showModal, setShowModal]             = useState<'user_to_admin' | 'admin_to_superadmin' | 'admin_to_user' | null>(null);
    const [showUserPicker, setShowUserPicker]   = useState(false);
    const [pickedUser, setPickedUser]           = useState<TenantUser | null>(null);
    const [escalationSource, setEscalationSource] = useState<SupportConversation | null>(null);

    const [typingUsers, setTypingUsers]   = useState<string[]>([]);
    const [presence, setPresence]         = useState<Record<string, boolean>>({});
    const typingTimerRef                  = useRef<ReturnType<typeof setTimeout> | null>(null);
    const bottomRef                       = useRef<HTMLDivElement>(null);

    // ── Load conversation list ────────────────────────────────────────────────
    const loadList = useCallback(async () => {
        setLoading(true);
        try {
            const params: Record<string, string> = {};
            if (filter !== 'all') params.status = filter === 'open' ? 'open' : 'resolved';
            const data = await fetchSupportConversations(params);
            setConvos(Array.isArray(data) ? data : []);
        } finally { setLoading(false); }
    }, [filter]);

    useEffect(() => { loadList(); }, [loadList]);

    // ── Deep-link: auto-open a conversation requested from outside the panel ────
    // (e.g. an admin started a direct chat and the user clicked the toast). The
    // thread is fetched by id directly, so it opens even before the list poll
    // surfaces it; we also refresh the list so it appears in the sidebar.
    useEffect(() => {
        if (!initialConvoId) return;
        setActiveId(initialConvoId);
        loadList();
        onConvoConsumed?.();
    }, [initialConvoId]); // eslint-disable-line react-hooks/exhaustive-deps

    // ── Load active conversation ──────────────────────────────────────────────
    useEffect(() => {
        if (!activeId) { setActiveConvo(null); return; }
        fetchSupportConversation(activeId).then(setActiveConvo).catch(() => {});
    }, [activeId]);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [activeConvo?.messages?.length]);

    // ── Polling fallback ──────────────────────────────────────────────────────
    useEffect(() => {
        if (!activeId) return;
        const id = setInterval(async () => {
            try {
                const fresh = await fetchSupportConversation(activeId);
                setActiveConvo(prev => {
                    if (!prev) return fresh;
                    if ((fresh.messages ?? []).length === (prev.messages ?? []).length &&
                        fresh.status === prev.status) return prev;
                    return fresh;
                });
            } catch { /* ignore */ }
        }, 3000);
        return () => clearInterval(id);
    }, [activeId]);

    useEffect(() => {
        const id = setInterval(loadList, 8000);
        return () => clearInterval(id);
    }, [loadList]);

    // ── Typing indicators ─────────────────────────────────────────────────────
    useEffect(() => {
        const handler = (data: any) => {
            if (data.convo_id !== activeId) return;
            setTypingUsers(prev =>
                data.is_typing
                    ? prev.includes(data.username) ? prev : [...prev, data.username]
                    : prev.filter(u => u !== data.username)
            );
        };
        socketService.on('support_typing', handler);
        return () => { socketService.off('support_typing', handler); setTypingUsers([]); };
    }, [activeId]);

    // ── Mark conversation as read when opened / new message arrives ───────────
    useEffect(() => {
        if (activeId) markSupportConversationRead(activeId);
    }, [activeId, activeConvo?.messages?.length]);

    // ── Presence polling (every 15s) ──────────────────────────────────────────
    useEffect(() => {
        if (!activeConvo) { setPresence({}); return; }
        const targets = activeConvo.chat_type === 'user_to_admin'
            ? [activeConvo.initiator_id]
            : activeConvo.target_user_id ? [activeConvo.target_user_id] : [];
        if (!targets.length) return;
        const check = () => fetchSupportPresence(targets).then(setPresence);
        check();
        const id = setInterval(check, 15000);
        return () => clearInterval(id);
    }, [activeConvo?.id]);

    // ── Real-time injection ───────────────────────────────────────────────────
    useEffect(() => {
        const handler = (data: any) => {
            if (data.event === 'new_message') {
                if (data.convo_id === activeId) {
                    setActiveConvo(prev => {
                        if (!prev) return prev;
                        const alreadyHas = (prev.messages ?? []).some(m => m.id === data.message.id);
                        if (alreadyHas) return prev;
                        return { ...prev, messages: [...(prev.messages ?? []), data.message] };
                    });
                }
                setConvos(prev => prev.map(c =>
                    c.id === data.convo_id
                        ? { ...c, last_message: data.message, status: 'in_progress' }
                        : c
                ));
            }
            if (data.event === 'new_conversation') loadList();
            if (data.event === 'read_receipt' && data.convo_id === activeId) {
                setActiveConvo(prev => prev
                    ? { ...prev, readers: { ...(prev.readers ?? {}), [data.reader]: data.at } }
                    : prev
                );
            }
        };
        socketService.on('support_message', handler);
        return () => socketService.off('support_message', handler);
    }, [activeId, loadList]);

    // ── Send message ──────────────────────────────────────────────────────────
    const handleSend = async () => {
        if (!activeId || !input.trim() || sending) return;
        const content = input.trim();
        setInput('');
        setSending(true);
        try {
            const msg = await sendSupportMessage(activeId, content);
            setActiveConvo(prev => prev ? { ...prev, messages: [...(prev.messages ?? []), msg] } : prev);
            setConvos(prev => prev.map(c => c.id === activeId ? { ...c, last_message: msg, status: 'in_progress' } : c));
        } catch { setInput(content); }
        finally { setSending(false); }
    };

    const handleResolve = async () => {
        if (!activeId) return;
        const updated = await updateSupportStatus(activeId, 'resolved');
        setActiveConvo(updated);
        setConvos(prev => prev.map(c => c.id === activeId ? { ...c, status: 'resolved' } : c));
    };

    // When admin picks a user, show compose modal
    const handleUserPicked = (u: TenantUser) => {
        setPickedUser(u);
        setShowUserPicker(false);
        setShowModal('admin_to_user');
    };

    const filteredConvos = convos.filter(c => {
        if (filter === 'open')     return ['open', 'in_progress'].includes(c.status);
        if (filter === 'resolved') return ['resolved', 'closed'].includes(c.status);
        return true;
    });

    // ── Conversation header subtitle ──────────────────────────────────────────
    const convoSubtitle = (c: SupportConversation | null) => {
        if (!c) return '';
        if (c.chat_type === 'admin_to_superadmin') return 'Escalated to Super Admin';
        if (c.chat_type === 'admin_to_user') return `Direct message to ${c.target_user_name ?? c.target_user_id}`;
        const display = c.initiator_name ?? c.initiator_id;
        return `Opened by ${display}`;
    };

    // ── Resolve the 1:1 call peer for the active conversation ───────────────────
    // Calls are person-to-person, so they only apply to conversations with a
    // single identifiable counterpart (admin↔user). Pooled routes (a user
    // contacting "an admin", or admin→super-admin) have no single callee.
    const myName = (currentUser as any)?.name ?? myId;
    const callPeer: { username: string; name: string } | null = (() => {
        const c = activeConvo;
        if (!c) return null;
        if (c.chat_type === 'admin_to_user') {
            if (c.initiator_id === myId && c.target_user_id)
                return { username: c.target_user_id, name: c.target_user_name ?? c.target_user_id };
            if (c.target_user_id === myId)
                return { username: c.initiator_id, name: c.initiator_name ?? c.initiator_id };
            return null;
        }
        if (c.chat_type === 'user_to_admin' && isAdmin(role))
            return { username: c.initiator_id, name: c.initiator_name ?? c.initiator_id };
        return null;
    })();

    const startCall = (video: boolean) => {
        if (!callPeer || !activeConvo) return;
        webrtcCallService.startCall(callPeer.username, callPeer.name, activeConvo.id, video, myName);
    };

    return (
        <div className="flex h-full bg-slate-950 text-white overflow-hidden">

            {/* ── Left: conversation list ──────────────────────────────────── */}
            <div className="w-80 flex-shrink-0 border-r border-slate-800 flex flex-col">
                <div className="p-4 border-b border-slate-800">
                    <div className="flex items-center justify-between mb-3">
                        <h2 className="font-semibold text-base">Support</h2>
                        <div className="flex gap-2 flex-wrap justify-end">
                            {/* Regular user: contact support */}
                            {!isAdmin(role) && (
                                <button
                                    onClick={() => setShowModal('user_to_admin')}
                                    className="text-xs bg-teal-600 hover:bg-teal-500 text-white px-3 py-1 rounded-lg"
                                >+ New</button>
                            )}
                            {/* Tenant admin: escalate to super-admin */}
                            {isAdmin(role) && !isSuper(role) && (
                                <button
                                    onClick={() => setShowModal('admin_to_superadmin')}
                                    className="text-xs bg-purple-600 hover:bg-purple-500 text-white px-3 py-1 rounded-lg"
                                    title="Escalate to Super Admin"
                                >Escalate</button>
                            )}
                            {/* Admin: message a specific user */}
                            {isAdmin(role) && (
                                <button
                                    onClick={() => setShowUserPicker(true)}
                                    className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1 rounded-lg"
                                    title="Start a direct conversation with a user"
                                >Message User</button>
                            )}
                        </div>
                    </div>
                    {/* Filter tabs */}
                    <div className="flex gap-1 text-xs">
                        {(['all', 'open', 'resolved'] as const).map(f => (
                            <button
                                key={f} onClick={() => setFilter(f)}
                                className={`px-3 py-1 rounded-md capitalize transition-colors ${
                                    filter === f ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-white'
                                }`}
                            >{f}</button>
                        ))}
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto">
                    {loading && <p className="text-slate-500 text-sm p-4">Loading…</p>}
                    {!loading && filteredConvos.length === 0 && (
                        <div className="p-6 text-center text-slate-500 text-sm">
                            No conversations yet.
                            {!isAdmin(role) && (
                                <button
                                    onClick={() => setShowModal('user_to_admin')}
                                    className="block mx-auto mt-2 text-teal-400 hover:underline"
                                >Start one →</button>
                            )}
                        </div>
                    )}
                    {filteredConvos.map(c => (
                        <button
                            key={c.id}
                            onClick={() => setActiveId(c.id)}
                            className={`w-full text-left px-4 py-3 border-b border-slate-800 hover:bg-slate-800/50 transition-colors ${
                                activeId === c.id ? 'bg-slate-800' : ''
                            }`}
                        >
                            <div className="flex items-start justify-between gap-2 mb-1">
                                <span className="text-sm font-medium truncate flex-1">{c.subject}</span>
                                <StatusBadge status={c.status} />
                            </div>
                            <div className="flex items-center gap-2 text-[11px] text-slate-400 mb-1">
                                <ChatTypePill type={c.chat_type} />
                                {c.chat_type === 'admin_to_user' && (
                                    <span className="text-indigo-300 truncate">→ {c.target_user_name ?? c.target_user_id}</span>
                                )}
                                {c.chat_type === 'user_to_admin' && (
                                    <span className="text-teal-300 truncate">
                                        {c.initiator_name ?? c.initiator_id}
                                        {c.initiator_email && c.initiator_email !== (c.initiator_name ?? c.initiator_id) && (
                                            <span className="text-slate-500"> · {c.initiator_email}</span>
                                        )}
                                    </span>
                                )}
                                {c.chat_type === 'admin_to_superadmin' && c.original_user_name && (
                                    <span className="text-purple-300 truncate">re: {c.original_user_name}</span>
                                )}
                            </div>
                            <div className="text-[11px] text-slate-400 truncate">
                                {c.last_message?.content ?? 'No messages'}
                            </div>
                            <p className="text-[10px] text-slate-500 mt-1">
                                {new Date(c.updated_at).toLocaleDateString()}
                            </p>
                        </button>
                    ))}
                </div>
            </div>

            {/* ── Right: message thread ────────────────────────────────────── */}
            <div className="flex-1 flex flex-col">
                {!activeConvo ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-slate-500 gap-3">
                        <div className="text-4xl opacity-30">💬</div>
                        <p className="text-sm">Select a conversation</p>
                        {isAdmin(role) && (
                            <button
                                onClick={() => setShowUserPicker(true)}
                                className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg mt-1"
                            >+ Message a User</button>
                        )}
                    </div>
                ) : (
                    <>
                        {/* Header */}
                        <div className="px-5 py-3 border-b border-slate-800 bg-slate-900/50">
                            <div className="flex items-center justify-between gap-3">
                                <div className="min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <h3 className="font-semibold text-sm truncate">{activeConvo.subject}</h3>
                                        <ChatTypePill type={activeConvo.chat_type} />
                                    </div>
                                    {activeConvo.chat_type !== 'user_to_admin' && (
                                        <p className="text-xs text-slate-400 mt-0.5">{convoSubtitle(activeConvo)}</p>
                                    )}
                                </div>
                                <div className="flex items-center gap-3 flex-shrink-0">
                                    {/* Show user identity card to admins when a user contacts support */}
                                    {isAdmin(role) && activeConvo.chat_type === 'user_to_admin' && (
                                        <UserIdentityCard
                                            convo={activeConvo}
                                            isOnline={presence[activeConvo.initiator_id]}
                                        />
                                    )}
                                    <StatusBadge status={activeConvo.status} />
                                    {/* Audio / video call — only for 1:1 admin↔user conversations */}
                                    {callPeer && !['resolved', 'closed'].includes(activeConvo.status) && (
                                        <>
                                            <button
                                                onClick={() => startCall(false)}
                                                title={`Voice call ${callPeer.name}`}
                                                aria-label={`Voice call ${callPeer.name}`}
                                                className="text-xs bg-emerald-700 hover:bg-emerald-600 text-white w-8 h-8 rounded-lg flex items-center justify-center"
                                            >
                                                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.98.36 1.94.7 2.86a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.22-1.22a2 2 0 0 1 2.11-.45c.92.34 1.88.57 2.86.7A2 2 0 0 1 22 16.92z"/></svg>
                                            </button>
                                            <button
                                                onClick={() => startCall(true)}
                                                title={`Video call ${callPeer.name}`}
                                                aria-label={`Video call ${callPeer.name}`}
                                                className="text-xs bg-emerald-700 hover:bg-emerald-600 text-white w-8 h-8 rounded-lg flex items-center justify-center"
                                            >
                                                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m23 7-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>
                                            </button>
                                        </>
                                    )}
                                    {/* Escalate button — admins chatting with a user can escalate to super admin */}
                                    {isAdmin(role) && !isSuper(role) && activeConvo.chat_type === 'user_to_admin' && !['resolved', 'closed'].includes(activeConvo.status) && (
                                        <button
                                            onClick={() => { setEscalationSource(activeConvo); setShowModal('admin_to_superadmin'); }}
                                            className="text-xs bg-purple-700 hover:bg-purple-600 text-white px-3 py-1 rounded-lg"
                                        >Escalate ↑</button>
                                    )}
                                    {isAdmin(role) && !['resolved', 'closed'].includes(activeConvo.status) && (
                                        <button
                                            onClick={handleResolve}
                                            className="text-xs bg-green-700 hover:bg-green-600 text-white px-3 py-1 rounded-lg"
                                        >Mark Resolved</button>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Escalation context banner — shown to super admins on escalated conversations */}
                        {activeConvo.chat_type === 'admin_to_superadmin' && activeConvo.original_convo_id && (
                            <div className="px-5 py-2.5 bg-purple-950/50 border-b border-purple-700/30 flex items-center gap-3 text-xs">
                                <span className="text-purple-400 font-semibold whitespace-nowrap">Escalated issue:</span>
                                <span className="text-white font-medium truncate">{activeConvo.original_subject}</span>
                                <span className="text-purple-300/60 mx-1">·</span>
                                <span className="text-purple-200 whitespace-nowrap">
                                    {activeConvo.original_user_name}
                                    {activeConvo.original_user_email && (
                                        <span className="text-purple-300/60"> · {activeConvo.original_user_email}</span>
                                    )}
                                </span>
                            </div>
                        )}

                        {/* Messages */}
                        <div className="flex-1 overflow-y-auto px-5 py-4">
                            {(activeConvo.messages ?? []).map((msg, i, arr) => {
                                const isMine = msg.sender_id === myId;
                                const isLast = i === arr.length - 1;
                                // "Seen" — show under the last message I sent if the other side read it
                                const otherReader = Object.entries(activeConvo.readers ?? {})
                                    .find(([u, t]) => u !== myId && t >= msg.created_at);
                                const showSeen = isMine && isLast && !!otherReader;
                                return (
                                    <React.Fragment key={msg.id}>
                                        <Bubble msg={msg} isMine={isMine} />
                                        {showSeen && (
                                            <div className="flex justify-end mb-1 -mt-2 pr-1">
                                                <span className="text-[10px] text-teal-400/70">Seen</span>
                                            </div>
                                        )}
                                    </React.Fragment>
                                );
                            })}
                            {/* Typing indicator bubble */}
                            {typingUsers.length > 0 && (
                                <div className="flex justify-start mb-3">
                                    <div className="bg-slate-700 rounded-2xl rounded-bl-sm px-4 py-3">
                                        <div className="flex gap-1 items-center">
                                            {[0, 150, 300].map(delay => (
                                                <span key={delay} className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce"
                                                    style={{ animationDelay: `${delay}ms` }} />
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            )}
                            <div ref={bottomRef} />
                        </div>

                        {/* Input */}
                        {['resolved', 'closed'].includes(activeConvo.status) ? (
                            <div className="px-5 py-3 border-t border-slate-800 text-center text-xs text-slate-500">
                                This conversation is {activeConvo.status}.
                            </div>
                        ) : (
                            <div className="px-5 py-3 border-t border-slate-800 flex items-end gap-3 bg-slate-900/30">
                                <textarea
                                    rows={2}
                                    value={input}
                                    onChange={e => {
                                        setInput(e.target.value);
                                        if (activeId) {
                                            socketService.sendTyping(activeId, true);
                                            if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
                                            typingTimerRef.current = setTimeout(() => {
                                                socketService.sendTyping(activeId, false);
                                            }, 2000);
                                        }
                                    }}
                                    onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                                    placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
                                    className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-teal-500 resize-none"
                                />
                                <button
                                    onClick={handleSend}
                                    disabled={sending || !input.trim()}
                                    className="px-4 py-2.5 bg-teal-600 hover:bg-teal-500 text-white text-sm rounded-xl disabled:opacity-40 flex-shrink-0"
                                >{sending ? '…' : 'Send'}</button>
                            </div>
                        )}
                    </>
                )}
            </div>

            {/* ── Modals ───────────────────────────────────────────────────── */}
            {showUserPicker && (
                <UserPickerModal
                    onSelect={handleUserPicked}
                    onClose={() => setShowUserPicker(false)}
                />
            )}

            {showModal && (
                <NewConvoModal
                    chatType={showModal}
                    targetUser={showModal === 'admin_to_user' ? pickedUser : null}
                    originalConvo={showModal === 'admin_to_superadmin' ? escalationSource : null}
                    onClose={() => { setShowModal(null); setPickedUser(null); setEscalationSource(null); }}
                    onCreate={c => { setConvos(prev => [c, ...prev]); setActiveId(c.id); }}
                />
            )}
        </div>
    );
};

export default SupportChatPanel;
