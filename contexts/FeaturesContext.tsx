/**
 * FeaturesContext
 * ───────────────
 * Loads the current tenant's effective feature set from the backend once on
 * login, then exposes hasFeature(key) to the whole component tree.
 *
 * Usage:
 *   const { hasFeature, features, loading } = useFeatures();
 *   if (!hasFeature('finops')) return <UpgradePrompt />;
 */

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { PlatformFeature, TenantFeatures } from '../types';
import { useUser } from './UserContext';
import { API_BASE } from '../services/apiService';

// ── Core-tier features always available regardless of backend response ──────
const ALWAYS_ON = new Set([
  'dashboard', 'tickets', 'agents', 'assets', 'users',
  'settings', 'audit_log', 'knowledge_base', 'support_chat',
]);

interface FeaturesContextValue {
  /** True if the current tenant has this feature key */
  hasFeature: (key: string) => boolean;
  /** Full list of effective features for this tenant */
  features: PlatformFeature[];
  /** Feature keys as a plain Set for quick lookups */
  featureKeys: Set<string>;
  /** Bundles assigned to the current tenant */
  assignedBundles: string[];
  /** True while the initial fetch is in flight */
  loading: boolean;
  /** Re-fetch after a bundle assignment change */
  refresh: () => void;
}

const FeaturesContext = createContext<FeaturesContextValue>({
  hasFeature: () => true,
  features: [],
  featureKeys: new Set(),
  assignedBundles: [],
  loading: false,
  refresh: () => {},
});

export const FeaturesProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const userCtx = useUser();
  const currentUser = userCtx?.currentUser;

  const [tenantFeatures, setTenantFeatures] = useState<TenantFeatures | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchFeatures = useCallback(async () => {
    const tid = currentUser?.tenantId;
    if (!tid) return;
    setLoading(true);
    try {
      const token = sessionStorage.getItem('token') || '';
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const res = await fetch(`${API_BASE}/bundles/tenant/${tid}/features`, { headers });
      if (res.ok) {
        const data: TenantFeatures = await res.json();
        setTenantFeatures(data);
      }
      // Non-2xx → tenant has no bundles assigned → fall through to always-on
    } catch {
      // Network error — degrade gracefully to always-on features
    } finally {
      setLoading(false);
    }
  }, [currentUser?.tenantId]);

  useEffect(() => {
    fetchFeatures();
  }, [fetchFeatures]);

  const featureKeys = useMemo<Set<string>>(() => {
    const keys = new Set<string>(ALWAYS_ON);
    if (tenantFeatures?.feature_keys) {
      tenantFeatures.feature_keys.forEach(k => keys.add(k));
    }
    return keys;
  }, [tenantFeatures]);

  const hasFeature = useCallback(
    (key: string) => featureKeys.has(key),
    [featureKeys],
  );

  const value = useMemo<FeaturesContextValue>(() => ({
    hasFeature,
    features: tenantFeatures?.effective_features ?? [],
    featureKeys,
    assignedBundles: tenantFeatures?.assigned_bundles ?? [],
    loading,
    refresh: fetchFeatures,
  }), [hasFeature, tenantFeatures, featureKeys, loading, fetchFeatures]);

  return <FeaturesContext.Provider value={value}>{children}</FeaturesContext.Provider>;
};

export const useFeatures = () => useContext(FeaturesContext);
