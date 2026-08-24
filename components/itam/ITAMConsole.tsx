import React, { useState, useEffect } from 'react';
import { Asset, ItamSettings, Tenant } from '../../types';
import { fetchAssets, getItamSettings } from '../../services/apiService';
import { CatalogPanel } from './CatalogPanel';
import { LifecyclePanel } from './LifecyclePanel';
import { FinancePanel } from './FinancePanel';
import { PurchaseOrdersPanel } from './PurchaseOrdersPanel';
import { RequestsPanel } from './RequestsPanel';
import { LicensesPanel } from './LicensesPanel';
import { CompliancePanel } from './CompliancePanel';
import { SoftwareInventoryPanel } from './SoftwareInventoryPanel';
import { ReportsPanel } from './ReportsPanel';
import { ItamKpiPanel } from './ItamKpiPanel';
import { ActivityLogPanel } from './ActivityLogPanel';
import { BulkImportExportPanel } from './BulkImportExportPanel';
import { SettingsPanel } from './SettingsPanel';
import { SettingsIcon } from '../icons';
import { ItamI18nProvider, useItamT } from './itamI18n';

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

type Tab = 'catalog' | 'lifecycle' | 'finance' | 'purchaseOrders' | 'requests' | 'licenses' | 'compliance' | 'software' | 'reports' | 'activity' | 'data' | 'settings';

// Tab ids are stable identifiers kept in English — only the displayed labelKey lookup
// (routed through useItamT() below) is translated, never the id or the aria-current
// logic that compares against it.
const TABS: { id: Tab; labelKey: string }[] = [
  { id: 'catalog', labelKey: 'tabs.catalog' },
  { id: 'lifecycle', labelKey: 'tabs.lifecycle' },
  { id: 'finance', labelKey: 'tabs.finance' },
  { id: 'purchaseOrders', labelKey: 'tabs.purchaseOrders' },
  { id: 'requests', labelKey: 'tabs.requests' },
  { id: 'licenses', labelKey: 'tabs.licenses' },
  { id: 'compliance', labelKey: 'tabs.compliance' },
  { id: 'software', labelKey: 'tabs.software' },
  { id: 'reports', labelKey: 'tabs.reports' },
  { id: 'activity', labelKey: 'tabs.activity' },
  { id: 'data', labelKey: 'tabs.data' },
  { id: 'settings', labelKey: 'tabs.settings' },
];

interface ITAMConsoleProps {
  tenants?: Tenant[];
  isSuperAdminView?: boolean;
}

interface ItamConsoleBodyProps {
  tab: Tab;
  setTab: (tab: Tab) => void;
  tenants: Tenant[];
  isSuperAdminView: boolean;
  assets: Asset[];
  settings: ItamSettings;
  onSettingsSaved: (settings: ItamSettings) => void;
  reportFocus: string | null;
  setReportFocus: (key: string | null) => void;
}

// Rendered as a child of ItamI18nProvider (below) so useItamT() resolves the locale the
// provider was mounted with — a component cannot consume a context provider it renders
// itself, hence this split.
function ItamConsoleBody({ tab, setTab, tenants, isSuperAdminView, assets, settings, onSettingsSaved, reportFocus, setReportFocus }: ItamConsoleBodyProps) {
  const t = useItamT();
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
              {t('header.title')}{branding.companyName ? ` — ${branding.companyName}` : ''}
            </h1>
            <p className="text-gray-400 text-sm mt-1">{t('header.subtitle')}</p>
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
        {TABS.map((tabDef) => (
          <button
            key={tabDef.id}
            onClick={() => setTab(tabDef.id)}
            aria-current={tab === tabDef.id ? 'page' : undefined}
            style={tab === tabDef.id ? { borderBottomColor: accent } : undefined}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === tabDef.id
                ? 'border-cyan-500 text-white'
                : 'border-transparent text-gray-400 hover:text-gray-200'
            }`}
          >
            {t(tabDef.labelKey)}
          </button>
        ))}
      </nav>

      <main>
        {tab === 'catalog' && <CatalogPanel />}
        {tab === 'lifecycle' && <LifecyclePanel tenants={tenants} isSuperAdminView={isSuperAdminView} />}
        {tab === 'finance' && <FinancePanel tenants={tenants} isSuperAdminView={isSuperAdminView} />}
        {tab === 'purchaseOrders' && <PurchaseOrdersPanel />}
        {tab === 'requests' && <RequestsPanel />}
        {tab === 'licenses' && <LicensesPanel />}
        {tab === 'compliance' && <CompliancePanel assets={assets} />}
        {tab === 'software' && <SoftwareInventoryPanel />}
        {tab === 'reports' && (
          <>
            {/* KPI grid is the primary anchor (UI-SPEC visual-hierarchy note) —
                mounted above the report sections, D-18 drill-down wired
                through the console's existing reportFocus seam. */}
            <ItamKpiPanel onDrillDown={(reportKey) => setReportFocus(reportKey)} />
            <ReportsPanel focusReportKey={reportFocus} onFocusHandled={() => setReportFocus(null)} />
          </>
        )}
        {tab === 'activity' && <ActivityLogPanel />}
        {tab === 'data' && <BulkImportExportPanel />}
        {tab === 'settings' && <SettingsPanel onSaved={onSettingsSaved} />}
      </main>
    </div>
  );
}

// ITAM operator console (Phase 61, ITAM-UI-01): admin-gated single entry
// point over Phases 56-60's five backend surfaces, cloning
// NativeSecurityConsole.tsx's tabbed-AppView shape per 61-RESEARCH.md.
export default function ITAMConsole({ tenants = [], isSuperAdminView = false }: ITAMConsoleProps) {
  const [tab, setTab] = useState<Tab>('catalog');
  const [assets, setAssets] = useState<Asset[]>([]);
  const [settings, setSettings] = useState<ItamSettings>(DEFAULT_ITAM_SETTINGS);
  // The KPI drill-down seam (D-18) plan 72-07 attaches to: a KPI tile sets
  // this to a report key and switches to the Reports tab; ReportsPanel
  // auto-runs it on mount and clears it via onFocusHandled.
  const [reportFocus, setReportFocus] = useState<string | null>(null);

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

  return (
    <ItamI18nProvider locale={settings.locale}>
      <ItamConsoleBody
        tab={tab}
        setTab={setTab}
        tenants={tenants}
        isSuperAdminView={isSuperAdminView}
        assets={assets}
        settings={settings}
        onSettingsSaved={setSettings}
        reportFocus={reportFocus}
        setReportFocus={setReportFocus}
      />
    </ItamI18nProvider>
  );
}
