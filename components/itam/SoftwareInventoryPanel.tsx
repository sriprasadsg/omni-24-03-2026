import React, { useEffect, useState, useCallback } from 'react';
import { SoftwareInventoryTab } from '../SoftwareInventoryTab';
import { authFetch, API_BASE } from '../../services/apiService';
import { showToast } from '../../utils/toast';

// Fleet-wide software inventory, directly integrated per 61-CONTEXT.md — no
// asset-scoping needed, SoftwareInventoryTab already fetches/filters/groups
// by package across the whole fleet. Data-fetch wrapper cloned from
// SoftwareDeployment.tsx's fetchInventory/handleInventoryUninstall wiring.
export function SoftwareInventoryPanel() {
  const [inventory, setInventory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchInventory = useCallback(async () => {
    setLoading(true);
    try {
      const res = await authFetch(`${API_BASE}/software/inventory`);
      if (res.ok) setInventory(await res.json());
    } catch (e) {
      console.error('Failed to load software inventory', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchInventory(); }, [fetchInventory]);

  const handleUninstall = useCallback(async (packageId: string, agentIds: string[]) => {
    try {
      const res = await authFetch(`${API_BASE}/software/deploy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agentIds, packageId, action: 'uninstall' }),
      });
      const data = await res.json();
      if (data.success) {
        showToast(`Uninstall dispatched to ${agentIds.length} agent(s)`, 'success');
        setTimeout(fetchInventory, 3000);
      } else {
        showToast(data.error || 'Uninstall failed', 'error');
      }
    } catch (e: any) {
      showToast(e?.message || 'Uninstall failed', 'error');
    }
  }, [fetchInventory]);

  return (
    <SoftwareInventoryTab
      inventory={inventory}
      loading={loading}
      onRefresh={fetchInventory}
      onUninstall={handleUninstall}
    />
  );
}
