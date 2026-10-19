import React, { useMemo, useState, useEffect, useRef } from 'react';
import { BotIcon, ArrowLeftIcon } from './icons';
import { Lock, ChevronDown } from 'lucide-react';
import { AppView } from '../types';
import { useUser } from '../contexts/UserContext';
import { fetchSupportUnreadCount } from '../services/apiService';
import { socketService } from '../services/socketService';
import { isSuperAdminRoleName } from '../utils/permissions';
import { permissionsKnown } from '../utils/viewAccess';
import { useVisibleNav, openNavItems, NavGroup } from '../hooks/useVisibleNav';
import { useNavMemory, navMemoryKey } from '../hooks/useNavMemory';

interface SidebarProps {
    isOpen: boolean;
    currentView: AppView;
    setCurrentView: (view: AppView) => void;
    isViewingTenant: boolean;
    onBackToTenants: () => void;
    branding?: {
        logoUrl?: string;
        companyName?: string;
    };
}

const NavLink: React.FC<{
    icon: React.ReactNode; label: string; active?: boolean;
    onClick: () => void; disabled?: boolean; isOpen: boolean;
    locked?: string; badge?: number;
}> = ({ icon, label, active, onClick, disabled, isOpen, locked, badge }) => (
    <button
        onClick={locked ? undefined : onClick}
        disabled={disabled}
        title={locked ? `Requires ${locked} plan — click to upgrade` : (!isOpen ? label : undefined)}
        aria-current={active && !locked ? 'page' : undefined}
        className={`w-full flex items-center px-3 py-2 text-[13px] font-medium rounded-xl transition-all duration-200 relative group border
            ${locked ? 'opacity-40 cursor-not-allowed' : ''}
            ${active && !locked
                ? 'text-primary-700 dark:text-primary-300 bg-primary-500/10 dark:bg-primary-400/10 border-primary-500/20 dark:border-primary-400/20 shadow-[inset_0_1px_0_rgb(255_255_255/0.06)]'
                : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-900/[0.04] dark:hover:bg-white/[0.05]'
            } ${disabled && !locked ? 'opacity-40 cursor-not-allowed' : ''}`}
    >
        {/* Icon */}
        <div className={`relative flex-shrink-0 transition-all duration-200
            ${active && !locked ? 'text-primary-600 dark:text-primary-400 drop-shadow-[0_0_6px_rgb(34_211_238/0.45)]' : 'text-gray-500 dark:text-gray-500 group-hover:text-gray-700 dark:group-hover:text-gray-300'}`}>
            {icon}
            {!isOpen && !!badge && badge > 0 && (
                <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-red-500 text-[8px] font-bold text-white">
                    {badge > 9 ? '9+' : badge}
                </span>
            )}
        </div>

        {isOpen && (
            <span className="ml-3 truncate flex-1 text-left tracking-tight">{label}</span>
        )}

        {isOpen && locked && (
            <span className="ml-auto flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-md"
                style={{ background: 'rgba(217,119,6,0.15)', color: '#fbbf24', border: '1px solid rgba(217,119,6,0.25)' }}>
                <Lock size={9} />{locked}
            </span>
        )}

        {isOpen && !locked && !!badge && badge > 0 && (
            <span className="ml-auto flex-shrink-0 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white px-1">
                {badge > 99 ? '99+' : badge}
            </span>
        )}

        {/* Gradient active bar */}
        {!locked && active && (
            <div aria-hidden="true" className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full -ml-[13px] bg-primary-500 dark:bg-primary-400 shadow-[0_0_12px_rgb(34_211_238/0.8)]" />
        )}
    </button>
);

// ─── Accordion Group ────────────────────────────────────────────────────────
const SidebarGroup: React.FC<{
    group: NavGroup;
    groupIndex: number;
    isOpen: boolean;
    currentView: AppView;
    setCurrentView: (view: AppView) => void;
    expandedGroup: string | null;
    setExpandedGroup: (title: string | null) => void;
    badgeCounts?: Record<string, number>;
}> = ({ group, groupIndex, isOpen, currentView, setCurrentView, expandedGroup, setExpandedGroup, badgeCounts }) => {
    const isExpanded = expandedGroup === group.title;
    const hasActiveItem = group.items.some(i => i.view === currentView);
    const contentRef = useRef<HTMLDivElement>(null);

    // Auto-expand when this group contains the active view
    useEffect(() => {
        if (hasActiveItem) setExpandedGroup(group.title);
    }, [currentView]);

    const toggle = () => setExpandedGroup(isExpanded ? null : group.title);

    return (
        <div className="overflow-hidden">
            {/* ── Group Header (accordion toggle) ─────────────────────── */}
            {isOpen ? (
                <button
                    onClick={toggle}
                    aria-expanded={isExpanded}
                    className={`w-full flex items-center justify-between px-3 py-1.5 mb-0.5 rounded-lg
                        text-[11px] font-semibold uppercase tracking-[0.08em] select-none transition-all duration-200
                        ${isExpanded
                            ? 'text-primary-700 dark:text-primary-300'
                            : 'text-gray-500 dark:text-gray-500 hover:text-gray-800 dark:hover:text-gray-300 hover:bg-gray-900/[0.04] dark:hover:bg-white/[0.04]'
                        }`}
                >
                    <span className="truncate text-left">{group.title}</span>
                    <ChevronDown
                        size={13}
                        className={`flex-shrink-0 transition-transform duration-300 ${isExpanded ? 'rotate-180' : 'rotate-0'}`}
                    />
                </button>
            ) : (
                /* Collapsed sidebar — just a thin divider between groups */
                groupIndex > 0 && <div className="my-2 mx-3 border-t border-gray-900/[0.06] dark:border-white/[0.06]" />
            )}

            {/* ── Accordion Content (smooth slide) ─────────────────────── */}
            {/* max-height must fit every item (≈38px each) or the rest of a long
                group is clipped and can't be clicked; a fixed 1000px cut off
                half of Security (SecOps). */}
            <div
                ref={contentRef}
                style={{
                    maxHeight: (!isOpen || isExpanded) ? `${group.items.length * 44 + 8}px` : '0px',
                    opacity: (!isOpen || isExpanded) ? 1 : 0,
                    overflow: 'hidden',
                    transition: 'max-height 0.35s cubic-bezier(0.4,0,0.2,1), opacity 0.25s ease',
                }}
            >
                <div className="space-y-0.5 py-0.5">
                    {group.items.map(item => (
                        <NavLink
                            key={item.view}
                            icon={item.icon}
                            label={item.label}
                            active={currentView === item.view}
                            onClick={() => setCurrentView(item.view)}
                            isOpen={isOpen}
                            locked={item.locked as string | undefined}
                            badge={badgeCounts?.[item.view]}
                        />
                    ))}
                </div>
            </div>
        </div>
    );
};

export const Sidebar: React.FC<SidebarProps> = ({ isOpen, currentView, setCurrentView, isViewingTenant, onBackToTenants, branding }) => {
    const userContext = useUser();
    const currentUser = userContext?.currentUser;

    // ── Accordion state: which group header is currently open ──────────────
    const [expandedGroup, setExpandedGroup] = useState<string | null>(null);

    // ── Chat unread badge (support + endpoint combined) ───────────────────
    const [supportUnread, setSupportUnread]   = useState(0);
    const [endpointUnread, setEndpointUnread] = useState(0);
    useEffect(() => {
        const fetch = () => fetchSupportUnreadCount().then(setSupportUnread).catch(() => {});
        fetch();
        const id = setInterval(fetch, 30_000);
        return () => clearInterval(id);
    }, []);
    useEffect(() => {
        const handler = (data: any) => {
            if (data.event === 'agent_chat_message' || data.event === 'agent_chat_initiated') {
                setEndpointUnread(prev => prev + 1);
            }
        };
        // Reset endpoint badge whenever user navigates to chat
        if (['chat', 'agentChat'].includes(currentView)) setEndpointUnread(0);
        socketService.on('agent_chat', handler);
        return () => socketService.off('agent_chat', handler);
    }, [currentView]);

    const visibleGroups = useVisibleNav(isViewingTenant);

    // Pinned pages, in the order they were pinned; only pages still open to the user show.
    const { pinned } = useNavMemory(navMemoryKey(currentUser));
    const pinnedItems = useMemo(() => {
        const open = new Map(openNavItems(visibleGroups).map(i => [i.view, i]));
        return pinned.map(v => open.get(v)).filter((i): i is NonNullable<typeof i> => !!i);
    }, [pinned, visibleGroups]);

    return (
        <aside aria-label="Main navigation" className={`flex-shrink-0 glass-panel rounded-3xl flex flex-col overflow-hidden transition-all duration-300 ease-in-out z-40 ${isOpen ? 'w-64 max-md:fixed max-md:inset-y-2 max-md:left-2 max-md:shadow-2xl' : 'w-[76px]'} `} >
            {/* Logo Section */}
            <div className={`flex items-center h-16 px-4 border-b border-gray-900/[0.06] dark:border-white/[0.06] ${isOpen ? 'justify-start' : 'justify-center'}`} >
                {
                    branding?.logoUrl ? (
                        <img src={branding.logoUrl} alt="Logo" className="h-8 w-auto" />
                    ) : (
                        <div className="relative grid place-items-center h-9 w-9 rounded-xl bg-gradient-to-br from-primary-400 via-primary-500 to-blue-600 shadow-[0_0_0_1px_rgb(255_255_255/0.15)_inset,0_6px_20px_-6px_rgb(34_211_238/0.7)]">
                            <BotIcon className="text-white" size={20} />
                        </div>
                    )}
                {
                    isOpen && (
                        <div className="ml-3 flex flex-col justify-center">
                            <span className="font-semibold text-[15px] tracking-tight text-gray-900 dark:text-white leading-tight">
                                {branding?.companyName || 'Omni-Agent'}
                            </span>
                            <span className="text-[10px] text-gray-500 dark:text-gray-400 font-medium tracking-[0.18em]">
                                AI PLATFORM
                            </span>
                        </div>
                    )
                }
            </div>

            {/* Navigation Section */}
            <nav className="flex-1 overflow-y-auto overflow-x-hidden px-3 py-4 space-y-4" >

                {/* Back to Tenants Link */}
                {
                    !!currentUser && isSuperAdminRoleName(currentUser.role) && isViewingTenant && (
                        <div className="mb-2">
                            <button
                                onClick={onBackToTenants}
                                className={`w-full flex items-center px-3 py-2.5 text-sm font-medium rounded-lg
bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400
hover:bg-amber-100 dark:hover:bg-amber-900/30 transition-colors border border-amber-200 dark:border-amber-900/30
                            ${!isOpen && 'justify-center'} `}
                                title="Back to Tenant List"
                            >
                                <ArrowLeftIcon size={18} />
                                {isOpen && <span className="ml-3">Back to Tenants</span>}
                            </button>
                        </div>
                    )
                }

                {/* Permissions not delivered yet: placeholders, never a guessed menu */}
                {
                    !permissionsKnown(currentUser ?? null) && (
                        <div className="space-y-2" aria-busy="true">
                            {Array.from({ length: 6 }, (_, i) => (
                                <div
                                    key={i}
                                    data-testid="sidebar-skeleton-row"
                                    className={isOpen
                                        ? 'h-8 rounded-xl bg-gray-200 dark:bg-gray-700 animate-pulse'
                                        : 'h-8 w-8 mx-auto rounded-full bg-gray-200 dark:bg-gray-700 animate-pulse'}
                                />
                            ))}
                        </div>
                    )
                }

                {/* Pinned pages (pin from the header star or the command palette) */}
                {
                    permissionsKnown(currentUser ?? null) && pinnedItems.length > 0 && (
                        <div role="group" aria-label="Pinned pages">
                            {isOpen
                                ? <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-gray-500 dark:text-gray-500">Pinned</p>
                                : <div className="mb-2 mx-3 border-t border-primary-500/30" />}
                            <div className="space-y-0.5">
                                {pinnedItems.map(item => (
                                    <NavLink
                                        key={`pin-${item.view}`}
                                        icon={item.icon}
                                        label={item.label}
                                        active={currentView === item.view}
                                        onClick={() => setCurrentView(item.view)}
                                        isOpen={isOpen}
                                    />
                                ))}
                            </div>
                        </div>
                    )
                }

                {/* Navigation Groups */}
                {
                    permissionsKnown(currentUser ?? null) && visibleGroups.map((group, groupIndex) => (
                        <SidebarGroup
                            key={group.title}
                            group={group}
                            groupIndex={groupIndex}
                            isOpen={isOpen}
                            currentView={currentView}
                            setCurrentView={setCurrentView}
                            expandedGroup={expandedGroup}
                            setExpandedGroup={setExpandedGroup}
                            badgeCounts={{ chat: supportUnread + endpointUnread }}
                        />
                    ))
                }
            </nav>

            {/* User Profile / Footer Section */}
            <div className="px-4 py-3 border-t border-gray-900/[0.06] dark:border-white/[0.06]" >
                {branding?.companyName && isOpen && (
                    <div className="text-[11px] text-gray-400 dark:text-gray-500">
                        © 2024 {branding.companyName}
                    </div>
                )}
            </div>
        </aside>
    );
};
