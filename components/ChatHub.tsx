import React, { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { Monitor, MessageSquare } from 'lucide-react';
import { socketService } from '../services/socketService';
import { fetchSupportUnreadCount } from '../services/apiService';

const AgentChatPanel  = lazy(() => import('./AgentChatPanel'));
const SupportChatPanel = lazy(() => import('./SupportChatPanel'));

type ChatTab = 'endpoint' | 'support';

// ── Tab button ─────────────────────────────────────────────────────────────

const TabBtn: React.FC<{
    active: boolean;
    label: string;
    icon: React.ReactNode;
    unread: number;
    onClick: () => void;
}> = ({ active, label, icon, unread, onClick }) => (
    <button
        onClick={onClick}
        className={`relative flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-lg transition-colors ${
            active
                ? 'bg-slate-700 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
        }`}
    >
        {icon}
        {label}
        {unread > 0 && (
            <span className="absolute -top-1.5 -right-1.5 min-w-[20px] h-5 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center px-1 shadow-lg animate-pulse">
                {unread > 99 ? '99+' : unread}
            </span>
        )}
    </button>
);

// ── Main hub ───────────────────────────────────────────────────────────────

interface ChatHubProps {
    initialTab?: ChatTab;
}

const ChatHub: React.FC<ChatHubProps> = ({ initialTab = 'endpoint' }) => {
    const [activeTab, setActiveTab]         = useState<ChatTab>(initialTab);
    const [endpointUnread, setEndpointUnread] = useState(0);
    const [supportUnread, setSupportUnread]   = useState(0);

    // Fetch initial support unread count
    useEffect(() => {
        fetchSupportUnreadCount().then(setSupportUnread).catch(() => {});
    }, []);

    // Endpoint chat: new message or new endpoint-initiated session
    useEffect(() => {
        const handler = (data: any) => {
            if (activeTab === 'endpoint') return;
            if (data.event === 'agent_chat_message' || data.event === 'agent_chat_initiated') {
                setEndpointUnread(prev => prev + 1);
            }
        };
        socketService.on('agent_chat', handler);
        return () => socketService.off('agent_chat', handler);
    }, [activeTab]);

    // Support chat: new message
    useEffect(() => {
        const handler = (data: any) => {
            if (activeTab === 'support') return;
            if (data.event === 'new_message') {
                setSupportUnread(prev => prev + 1);
            }
        };
        socketService.on('support_message', handler);
        return () => socketService.off('support_message', handler);
    }, [activeTab]);

    const switchTab = useCallback((tab: ChatTab) => {
        setActiveTab(tab);
        if (tab === 'endpoint') setEndpointUnread(0);
        if (tab === 'support')  setSupportUnread(0);
    }, []);

    return (
        <div className="flex flex-col h-full bg-slate-950 text-white overflow-hidden">

            {/* ── Tab bar ──────────────────────────────────────────────── */}
            <div className="flex items-center gap-2 px-4 py-2.5 border-b border-slate-800 bg-slate-900/60 flex-shrink-0">
                <TabBtn
                    active={activeTab === 'endpoint'}
                    label="Endpoint Chat"
                    icon={<Monitor size={15} />}
                    unread={endpointUnread}
                    onClick={() => switchTab('endpoint')}
                />
                <TabBtn
                    active={activeTab === 'support'}
                    label="Support Chat"
                    icon={<MessageSquare size={15} />}
                    unread={supportUnread}
                    onClick={() => switchTab('support')}
                />
                <div className="ml-auto text-[11px] text-slate-500">
                    {endpointUnread + supportUnread > 0
                        ? <span className="text-red-400">{endpointUnread + supportUnread} unread</span>
                        : 'All caught up'}
                </div>
            </div>

            {/*
              Both panels stay mounted so their polling timers, selected
              conversation and scroll position are preserved on tab switch.
              CSS display-none hides the inactive one from view.
            */}
            <div className={`flex-1 overflow-hidden min-h-0 ${activeTab === 'endpoint' ? 'flex' : 'hidden'}`}>
                <Suspense fallback={<div className="flex-1 flex items-center justify-center text-slate-500 text-sm">Loading…</div>}>
                    <AgentChatPanel />
                </Suspense>
            </div>
            <div className={`flex-1 overflow-hidden min-h-0 ${activeTab === 'support' ? 'flex' : 'hidden'}`}>
                <Suspense fallback={<div className="flex-1 flex items-center justify-center text-slate-500 text-sm">Loading…</div>}>
                    <SupportChatPanel />
                </Suspense>
            </div>
        </div>
    );
};

export default ChatHub;
