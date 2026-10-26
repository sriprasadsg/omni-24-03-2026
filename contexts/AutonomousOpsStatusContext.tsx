import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useUser } from './UserContext';
import { isSuperAdminRoleName, platformTier } from '../utils/permissions';
import {
    AutonomousOpsStatus, PlatformAutonomousOpsStatus,
    fetchAutonomousOpsStatus, fetchPlatformAutonomousOpsStatus,
} from '../services/autonomousOpsApi';

export const STATUS_POLL_MS = 30_000;

export type AutonomousOpsScope =
    | { kind: 'tenant'; tenantId: string | null }
    | { kind: 'platform' }
    | { kind: 'none' };

/**
 * Which data the viewer reads. Tenant roles always read their own tenant (no tenantId is sent;
 * the server decides). Platform staff read the tenant they entered from Tenants. Super Admin with
 * none selected reads the platform scope; any other platform role with none selected reads nothing.
 */
export function resolveAutonomousOpsScope(role: string | null | undefined, viewingTenantId: string | null | undefined): AutonomousOpsScope {
    if (platformTier(role) === null) return { kind: 'tenant', tenantId: null };
    if (viewingTenantId) return { kind: 'tenant', tenantId: viewingTenantId };
    return isSuperAdminRoleName(role) ? { kind: 'platform' } : { kind: 'none' };
}

export interface AutonomousOpsStatusValue {
    status: AutonomousOpsStatus | null;
    platformStatus: PlatformAutonomousOpsStatus | null;
    /** True only while the first answer for the current scope is outstanding. */
    loading: boolean;
    /** True when the latest fetch failed; the last known status is kept. */
    error: boolean;
    refresh: () => Promise<void>;
}

const idle: AutonomousOpsStatusValue = {
    status: null, platformStatus: null, loading: false, error: false, refresh: async () => {},
};

const AutonomousOpsStatusContext = createContext<AutonomousOpsStatusValue>(idle);

interface ProviderProps {
    tenantId?: string | null;
    /** Only holders of view:autonomous_ops mount a poller; false makes no request at all. */
    enabled: boolean;
    children: React.ReactNode;
}

/** The one status poller shared by the Autonomous Ops screen and the app-wide stop banner. */
export const AutonomousOpsStatusProvider: React.FC<ProviderProps> = ({ tenantId = null, enabled, children }) => {
    const { currentUser } = useUser();
    const scope = useMemo(
        () => resolveAutonomousOpsScope(currentUser?.role, tenantId),
        [currentUser?.role, tenantId],
    );
    const scopeKey = scope.kind === 'tenant' ? `tenant:${scope.tenantId ?? ''}` : scope.kind;

    const [status, setStatus] = useState<AutonomousOpsStatus | null>(null);
    const [platformStatus, setPlatformStatus] = useState<PlatformAutonomousOpsStatus | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(false);
    const generation = useRef(0);

    const load = useCallback(async () => {
        if (!enabled || scope.kind === 'none') return;
        const mine = generation.current;
        try {
            if (scope.kind === 'platform') {
                const next = await fetchPlatformAutonomousOpsStatus();
                if (mine !== generation.current) return;
                setPlatformStatus(next);
            } else {
                const next = await fetchAutonomousOpsStatus(scope.tenantId);
                if (mine !== generation.current) return;
                setStatus(next);
            }
            setError(false);
        } catch {
            if (mine !== generation.current) return;
            setError(true); // keep the last known state
        } finally {
            if (mine === generation.current) setLoading(false);
        }
    }, [enabled, scope]);

    useEffect(() => {
        generation.current += 1; // answers for the previous scope are dropped
        setStatus(null);
        setPlatformStatus(null);
        setError(false);
        if (!enabled || scope.kind === 'none') {
            setLoading(false);
            return;
        }
        setLoading(true);
        void load();

        let timer: ReturnType<typeof setInterval> | null = null;
        const visible = () => typeof document === 'undefined' || document.visibilityState !== 'hidden';
        const start = () => {
            if (timer === null) timer = setInterval(() => { void load(); }, STATUS_POLL_MS);
        };
        const stop = () => {
            if (timer !== null) { clearInterval(timer); timer = null; }
        };
        const onVisibility = () => {
            if (visible()) { void load(); start(); } else { stop(); }
        };
        const onFocus = () => { void load(); };

        if (visible()) start();
        document.addEventListener('visibilitychange', onVisibility);
        window.addEventListener('focus', onFocus);
        return () => {
            stop();
            document.removeEventListener('visibilitychange', onVisibility);
            window.removeEventListener('focus', onFocus);
            generation.current += 1;
        };
        // scopeKey stands in for the scope object so identical scopes do not restart the poller
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [enabled, scopeKey, load]);

    const value = useMemo<AutonomousOpsStatusValue>(
        () => ({ status, platformStatus, loading, error, refresh: load }),
        [status, platformStatus, loading, error, load],
    );
    return <AutonomousOpsStatusContext.Provider value={value}>{children}</AutonomousOpsStatusContext.Provider>;
};

export const useAutonomousOpsStatus = () => useContext(AutonomousOpsStatusContext);
