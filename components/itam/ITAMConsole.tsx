import React, { useState, useEffect } from 'react';
import { Asset, Tenant } from '../../types';
import { fetchAssets } from '../../services/apiService';
import { CatalogPanel } from './CatalogPanel';
import { LifecyclePanel } from './LifecyclePanel';
import { FinancePanel } from './FinancePanel';
import { LicensesPanel } from './LicensesPanel';
import { CompliancePanel } from './CompliancePanel';
import { SoftwareInventoryPanel } from './SoftwareInventoryPanel';
import { ActivityLogPanel } from './ActivityLogPanel';
import { BulkImportExportPanel } from './BulkImportExportPanel';
import { SettingsPanel } from './SettingsPanel';

type Tab = 'catalog' | 'lifecycle' | 'finance' | 'licenses' | 'compliance' | 'software' | 'activity' | 'data' | 'settings';

const TABS: { id: Tab; label: string }[] = [
  { id: 'catalog', label: 'Catalog' },
  { id: 'lifecycle', label: 'Check-Out/In' },
  { id: 'finance', label: 'Procurement & Finance' },
  { id: 'licenses', label: 'Licenses & Consumables' },
  { id: 'compliance', label: 'Compliance' },
  { id: 'software', label: 'Software Inventory' },
  { id: 'activity', label: 'Activity' },
  { id: 'data', label: 'Import / Export' },
  { id: 'settings', label: 'Settings' },
];

interface ITAMConsoleProps {
  tenants?: Tenant[];
  isSuperAdminView?: boolean;
}

// ITAM operator console (Phase 61, ITAM-UI-01): admin-gated single entry
// point over Phases 56-60's five backend surfaces, cloning
// NativeSecurityConsole.tsx's tabbed-AppView shape per 61-RESEARCH.md.
export default function ITAMConsole({ tenants = [], isSuperAdminView = false }: ITAMConsoleProps) {
  const [tab, setTab] = useState<Tab>('catalog');
  const [assets, setAssets] = useState<Asset[]>([]);

  // Shared with the Compliance tab so it doesn't independently refetch the
  // same fleet-wide asset list.
  useEffect(() => {
    fetchAssets().then((a) => setAssets(a || [])).catch(() => setAssets([]));
  }, []);

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">IT Asset Management Console</h1>
        <p className="text-gray-400 text-sm mt-1">
          Catalog, lifecycle, procurement, licenses, and compliance for every asset — agent-discovered and manually catalogued alike.
        </p>
      </header>

      <nav className="flex gap-1 mb-4 border-b border-gray-700" aria-label="Tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            aria-current={tab === t.id ? 'page' : undefined}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.id
                ? 'border-cyan-500 text-white'
                : 'border-transparent text-gray-400 hover:text-gray-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main>
        {tab === 'catalog' && <CatalogPanel />}
        {tab === 'lifecycle' && <LifecyclePanel tenants={tenants} isSuperAdminView={isSuperAdminView} />}
        {tab === 'finance' && <FinancePanel tenants={tenants} isSuperAdminView={isSuperAdminView} />}
        {tab === 'licenses' && <LicensesPanel />}
        {tab === 'compliance' && <CompliancePanel assets={assets} />}
        {tab === 'software' && <SoftwareInventoryPanel />}
        {tab === 'activity' && <ActivityLogPanel />}
        {tab === 'data' && <BulkImportExportPanel />}
        {tab === 'settings' && <SettingsPanel />}
      </main>
    </div>
  );
}
