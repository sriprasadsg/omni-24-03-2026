import React, { useMemo, useState, useEffect, useRef } from 'react';
import { BotIcon, ArrowLeftIcon } from './icons';
import { Lock, ChevronDown } from 'lucide-react';
import { AppView, Permission } from '../types';
import { NAV_GROUPS } from '../utils/catalogueAccess';
import { SIDEBAR_PRESENTATION } from './sidebarPresentation';
import { useUser } from '../contexts/UserContext';
import { useFeatures } from '../contexts/FeaturesContext';
import { fetchSupportUnreadCount } from '../services/apiService';
import { socketService } from '../services/socketService';
import { isPlatformRoleName, isSuperAdminRoleName, isTenantSwitchable } from '../utils/permissions';
import { evaluateViewAccess, permissionsKnown } from '../utils/viewAccess';

// Tier precedence — matches backend TIER_ORDER
const TIER_ORDER: Record<string, number> = { Free: 0, Pro: 1, Enterprise: 2, Custom: 3 };
const tierMeetsMin = (current: string, min?: string) =>
    !min || (TIER_ORDER[current] ?? 0) >= (TIER_ORDER[min] ?? 0);

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

interface NavItem {
    view: AppView;
    label: string;
    icon: React.ReactNode;
    permission: Permission;
    minTier?: 'Pro' | 'Enterprise';
    featureKey?: string; // backend feature_flags.py key — used for server-confirmed locking
    locked?: string; // set at runtime by visibleGroups
}

interface NavGroup {
    title: string;
    items: NavItem[];
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
        className={`w-full flex items-center px-3 py-2 text-sm font-medium rounded-xl transition-all duration-200 relative group
            ${locked ? 'opacity-40 cursor-not-allowed' : ''}
            ${active && !locked
                ? 'text-primary-400'
                : 'text-slate-500 dark:text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            } ${disabled && !locked ? 'opacity-40 cursor-not-allowed' : ''}`}
        style={active && !locked ? {
            background: 'linear-gradient(135deg, rgba(14,165,233,0.12) 0%, rgba(3,105,161,0.06) 100%)',
            border: '1px solid rgba(14,165,233,0.18)',
        } : undefined}
    >
        {/* Icon */}
        <div className={`relative flex-shrink-0 transition-all duration-200
            ${active && !locked ? 'text-primary-400' : 'text-slate-500 dark:text-slate-500 group-hover:text-slate-700 dark:group-hover:text-slate-300'}`}>
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
            <div className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 rounded-r-full -ml-3"
                style={{ background: 'linear-gradient(to bottom, #0369a1, #075985)' }} />
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
                    className={`w-full flex items-center justify-between px-3 py-1.5 mb-0.5 rounded-md
                        text-xs font-semibold uppercase tracking-wider select-none transition-all duration-200
                        ${isExpanded
                            ? 'text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/20'
                            : 'text-gray-400 dark:text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/5'
                        }`}
                >
                    <span>{group.title}</span>
                    <ChevronDown
                        size={13}
                        className={`flex-shrink-0 transition-transform duration-300 ${isExpanded ? 'rotate-180' : 'rotate-0'}`}
                    />
                </button>
            ) : (
                /* Collapsed sidebar — just a thin divider between groups */
                groupIndex > 0 && <div className="my-2 border-t border-gray-100 dark:border-gray-800" />
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
    const hasPermission = userContext?.hasPermission || (() => false);
    const currentUser = userContext?.currentUser;
    const serverLockedFeatures = userContext?.serverLockedFeatures ?? {};
    const { hasFeature, assignedBundles } = useFeatures();
    const isBundleMode = assignedBundles.length > 0;

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

    const menuGroups: NavGroup[] = useMemo(() => NAV_GROUPS.map(group => ({
        title: group.title,
        items: group.items.map(item => ({
            view: item.view,
            label: item.label,
            permission: item.permission,
            icon: SIDEBAR_PRESENTATION[item.view]?.icon ?? null,
            minTier: SIDEBAR_PRESENTATION[item.view]?.minTier,
            featureKey: SIDEBAR_PRESENTATION[item.view]?.featureKey,
        })),
    })), []);

    const visibleGroups = useMemo(() => {
        // Fail closed: no resolved user, no menu (a wildcard grant cannot open it either).
        if (!currentUser) return [];
        const isSuperAdmin = !!currentUser && isSuperAdminRoleName(currentUser.role);
        const userTier: string = (currentUser as any)?.subscriptionTier || 'Free';

        // Tenant users see only what the Super Admin switched on for their tenant (spec C6) and
        // never an upgrade prompt: a plan-tier-gated item shows when its feature switch is on, and
        // stays hidden when no switch covers it (the view:dashboard extras below the tenant's tier).
        const isTenantUser = !isSuperAdmin && !isPlatformRoleName(currentUser?.role);
        const tierLock = (item: { featureKey?: string; minTier?: string }): string | undefined => {
            const serverMinTier = item.featureKey ? serverLockedFeatures[item.featureKey] : undefined;
            const clientLocked = item.minTier && !tierMeetsMin(userTier, item.minTier);
            return serverMinTier || (clientLocked ? item.minTier : undefined);
        };

        return menuGroups
            .map(group => ({
                ...group,
                items: group.items
                    .filter(item => {
                        if (isViewingTenant && item.permission === 'manage:tenants') return false;
                        if (!evaluateViewAccess(item.view, currentUser ?? null, hasPermission).allowed) return false;
                        if (isSuperAdmin) return true;
                        // Bundle mode: hide items whose feature the tenant hasn't been assigned
                        if (isBundleMode && item.featureKey && !hasFeature(item.featureKey)) return false;
                        if (isTenantUser && tierLock(item) && !isTenantSwitchable(item.permission, item.view)) return false;
                        return true;
                    })
                    .map(item => (isSuperAdmin || isTenantUser ? { ...item, locked: undefined } : { ...item, locked: tierLock(item) })),
            }))
            .filter(group => group.items.length > 0);
    }, [menuGroups, isViewingTenant, currentUser, hasPermission, serverLockedFeatures, isBundleMode, hasFeature]);

    return (
        <aside className={`flex-shrink-0 glass border-r-0 flex flex-col transition-all duration-300 ease-in-out z-40 ${isOpen ? 'w-64 max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:shadow-2xl' : 'w-20'} `} >
            {/* Logo Section */}
            <div className="flex items-center justify-center h-16 border-b border-white/5 bg-transparent" >
                {
                    branding?.logoUrl ? (
                        <img src={branding.logoUrl} alt="Logo" className="h-8 w-auto" />
                    ) : (
                        <div className="bg-gradient-to-tr from-primary-500 to-primary-700 p-1.5 rounded-lg shadow-lg shadow-primary-500/20">
                            <BotIcon className="text-white" size={24} />
                        </div>
                    )}
                {
                    isOpen && (
                        <div className="ml-3 flex flex-col justify-center">
                            <span className="font-bold text-gray-900 dark:text-gray-100 leading-tight">
                                {branding?.companyName || 'Omni-Agent'}
                            </span>
                            <span className="text-[10px] text-gray-500 dark:text-gray-400 font-medium tracking-wider">
                                AI PLATFORM
                            </span>
                        </div>
                    )
                }
            </div>

            {/* Navigation Section */}
            <nav className="flex-1 overflow-y-auto overflow-x-hidden scrollbar-thin scrollbar-thumb-gray-200 dark:scrollbar-thumb-gray-800 p-3 space-y-6" >

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

                {/* Navigation Groups */}
                {
                    visibleGroups.map((group, groupIndex) => (
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
            <div className="p-3 border-t border-white/5 bg-transparent" >
                {branding?.companyName && isOpen && (
                    <div className="text-xs text-center text-gray-400 dark:text-gray-600">
                        © 2024 {branding.companyName}
                    </div>
                )}
            </div>
        </aside>
    );
};
