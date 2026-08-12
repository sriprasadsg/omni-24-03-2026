import React, { useState, useEffect } from 'react';
import { Asset, ItamSettings, Tenant } from '../../types';
import { fetchAssets, getItamSettings } from '../../services/apiService';
import { CatalogPanel } from './CatalogPanel';
import { LifecyclePanel } from './LifecyclePanel';
import { FinancePanel } from './FinancePanel';
import { LicensesPanel } from './LicensesPanel';
import { CompliancePanel } from './CompliancePanel';
import { SoftwareInventoryPanel } from './SoftwareInventoryPanel';
import { ActivityLogPanel } from './ActivityLogPanel';
import { BulkImportExportPanel } from './BulkImportExportPanel';
import { SettingsPanel } from './SettingsPanel';
import { SettingsIcon } from '../icons';

// Built-in defaults an unconfigured/failed-to-load tenant renders with — kept in sync
// with itam_customization_service.py's DEFAULT_ITAM_SETTINGS by convention (both encode
// the console's pre-existing cyan accent so an unbranded tenant is pixel-identical to
// before this phase).
const DEFAULT_ITAM_SETTINGS: ItamSettings = {
  branding: { companyName: '', logoUrl: '', primaryColor: '#0891b2' },
  locale: 'en',
};

const HEX_COLOR_RE = /^#[0-9a-fA-F]{6}$/;
const ALLOWED_LOGO_PREFIXES = ['https://', 'http://', 'data:image/'];

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
  const [settings, setSettings] = useState<ItamSettings>(DEFAULT_ITAM_SETTINGS);

  // Shared with the Compliance tab so it doesn't independently refetch the
  // same fleet-wide asset list.
  useEffect(() => {
    fetchAssets().then((a) => setAssets(a || [])).catch(() => setAssets([]));
  }, []);

  // A settings-load failure must never blank the console — keep the built-in defaults
  // and continue rendering exactly as an unconfigured tenant would.
  useEffect(() => {
    getItamSettings().then((s) => setSettings(s)).catch(() => setSettings(DEFAULT_ITAM_SETTINGS));
  }, []);

  const { branding } = settings;
  // Re-checked on the client as defence in depth even though the server already enforces
  // this (65-04-PLAN.md T-65-04-02) — a malformed value must never reach a style attribute.
  const accent = HEX_COLOR_RE.test(branding.primaryColor) ? branding.primaryColor : DEFAULT_ITAM_SETTINGS.branding.primaryColor;
  const logoUrl = branding.logoUrl && ALLOWED_LOGO_PREFIXES.some((p) => branding.logoUrl.startsWith(p)) ? branding.logoUrl : '';

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          {logoUrl && (
            <img src={logoUrl} alt={branding.companyName || 'Logo'} className="h-10 w-10 object-contain rounded bg-gray-800" />
          )}
          <div>
            <h1 className="text-2xl font-semibold">
              IT Asset Management Console{branding.companyName ? ` — ${branding.companyName}` : ''}
            </h1>
            <p className="text-gray-400 text-sm mt-1">
              Catalog, lifecycle, procurement, licenses, and compliance for every asset — agent-discovered and manually catalogued alike.
            </p>
          </div>
        </div>
        <button
          onClick={() => setTab('settings')}
          aria-label="Open ITAM console settings"
          style={{ backgroundColor: accent }}
          className="flex-shrink-0 text-white p-2 rounded-lg hover:opacity-90 transition-opacity"
        >
          <SettingsIcon size={18} />
        </button>
      </header>

      <nav className="flex gap-1 mb-4 border-b border-gray-700" aria-label="Tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            aria-current={tab === t.id ? 'page' : undefined}
            style={tab === t.id ? { borderBottomColor: accent } : undefined}
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
        {tab === 'settings' && <SettingsPanel onSaved={setSettings} />}
      </main>
    </div>
  );
}
