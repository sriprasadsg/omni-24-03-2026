import React, { useMemo } from 'react';
import { AppView, Permission } from '../types';
import { NAV_GROUPS } from '../utils/catalogueAccess';
import { SIDEBAR_PRESENTATION } from '../components/sidebarPresentation';
import { useUser } from '../contexts/UserContext';
import { useFeatures } from '../contexts/FeaturesContext';
import { isPlatformRoleName, isSuperAdminRoleName, isTenantSwitchable } from '../utils/permissions';
import { evaluateViewAccess } from '../utils/viewAccess';

// Tier precedence — matches backend TIER_ORDER
const TIER_ORDER: Record<string, number> = { Free: 0, Pro: 1, Enterprise: 2, Custom: 3 };
const tierMeetsMin = (current: string, min?: string) =>
    !min || (TIER_ORDER[current] ?? 0) >= (TIER_ORDER[min] ?? 0);

export interface NavItem {
    view: AppView;
    label: string;
    icon: React.ReactNode;
    permission: Permission;
    minTier?: 'Pro' | 'Enterprise';
    featureKey?: string; // backend feature_flags.py key — used for server-confirmed locking
    locked?: string; // set at runtime: the plan an upgrade would need
}

export interface NavGroup {
    title: string;
    items: NavItem[];
}

const MENU_GROUPS: NavGroup[] = NAV_GROUPS.map(group => ({
    title: group.title,
    items: group.items.map(item => ({
        view: item.view,
        label: item.label,
        permission: item.permission,
        icon: SIDEBAR_PRESENTATION[item.view]?.icon ?? null,
        minTier: SIDEBAR_PRESENTATION[item.view]?.minTier,
        featureKey: SIDEBAR_PRESENTATION[item.view]?.featureKey,
    })),
}));

/**
 * The menu the signed-in user may see: the sidebar, the command palette and pinned/recent pages all
 * read this one list, so none of them can offer a page the others would hide. Fails closed: no
 * resolved user (or no permission function) means no menu.
 */
export function useVisibleNav(isViewingTenant: boolean): NavGroup[] {
    const userContext = useUser();
    const hasPermission = userContext?.hasPermission || (() => false);
    const currentUser = userContext?.currentUser;
    const serverLockedFeatures = userContext?.serverLockedFeatures ?? {};
    const { hasFeature, assignedBundles } = useFeatures();
    const isBundleMode = assignedBundles.length > 0;

    return useMemo(() => {
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

        return MENU_GROUPS
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
    }, [isViewingTenant, currentUser, hasPermission, serverLockedFeatures, isBundleMode, hasFeature]);
}

/** Every open (not plan-locked) page in the visible menu, flattened, with its group title. */
export function openNavItems(groups: NavGroup[]): (NavItem & { group: string })[] {
    return groups.flatMap(g => g.items.filter(i => !i.locked).map(i => ({ ...i, group: g.title })));
}
