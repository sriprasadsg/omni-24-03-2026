import React, { useEffect, useState } from 'react';
import { getItamSettings, saveItamSettings } from '../../services/apiService';
import { ItamSettings } from '../../types';
import { showToast } from '../../utils/toast';

const DEFAULT_SETTINGS: ItamSettings = {
  branding: { companyName: '', logoUrl: '', primaryColor: '#0891b2' },
  locale: 'en',
};

interface SettingsPanelProps {
  // Lets ITAMConsole.tsx update its own branding/locale state immediately on a
  // successful save, without a page reload (wired in Task 2).
  onSaved?: (settings: ItamSettings) => void;
}

// New, ITAM-console-scoped Settings tab (Phase 65 Plan 04, ITAM-SET-01/02/03) — clones
// TenantBrandingSettings.tsx's controlled-input + fetch-on-mount + handleSave shape, but
// calls getItamSettings/saveItamSettings and is deliberately a separate surface from that
// platform-level component (D-01, 65-04-PLAN.md).
export function SettingsPanel({ onSaved }: SettingsPanelProps) {
  const [settings, setSettings] = useState<ItamSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getItamSettings()
      .then((s) => { if (!cancelled) setSettings(s); })
      .catch((e: any) => { if (!cancelled) setError(e?.message || "Couldn't load ITAM settings"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const saved = await saveItamSettings(settings);
      setSettings(saved);
      showToast('ITAM settings saved.', 'success');
      onSaved?.(saved);
    } catch (e: any) {
      const message = e?.message || "Couldn't save ITAM settings";
      setError(message);
      showToast(message, 'error');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-xl space-y-6">
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
        <h2 className="text-sm font-semibold text-white mb-1">Branding</h2>
        <p className="text-gray-400 text-xs mb-4">
          Customize the ITAM console's company name, logo, and accent colour for this tenant.
        </p>

        {loading ? (
          <p className="text-gray-400 text-sm">Loading…</p>
        ) : (
          <div className="space-y-4">
            <div>
              <label htmlFor="itam-settings-company-name" className="block text-xs text-gray-500 mb-1">
                Company name
              </label>
              <input
                id="itam-settings-company-name"
                type="text"
                aria-label="Company name"
                value={settings.branding.companyName}
                onChange={(e) => setSettings({ ...settings, branding: { ...settings.branding, companyName: e.target.value } })}
                className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white w-full"
                placeholder="e.g. Acme Corp"
              />
            </div>

            <div>
              <label htmlFor="itam-settings-logo-url" className="block text-xs text-gray-500 mb-1">
                Logo URL
              </label>
              <input
                id="itam-settings-logo-url"
                type="text"
                aria-label="Logo URL"
                value={settings.branding.logoUrl}
                onChange={(e) => setSettings({ ...settings, branding: { ...settings.branding, logoUrl: e.target.value } })}
                className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white w-full"
                placeholder="https://example.com/logo.png"
              />
            </div>

            <div>
              <label htmlFor="itam-settings-primary-color" className="block text-xs text-gray-500 mb-1">
                Primary colour
              </label>
              <div className="flex items-center gap-3">
                <input
                  id="itam-settings-primary-color"
                  type="color"
                  aria-label="Primary colour picker"
                  value={/^#[0-9a-fA-F]{6}$/.test(settings.branding.primaryColor) ? settings.branding.primaryColor : '#0891b2'}
                  onChange={(e) => setSettings({ ...settings, branding: { ...settings.branding, primaryColor: e.target.value } })}
                  className="h-9 w-16 rounded border border-gray-700 cursor-pointer bg-gray-900"
                />
                <input
                  type="text"
                  aria-label="Primary colour hex value"
                  value={settings.branding.primaryColor}
                  onChange={(e) => setSettings({ ...settings, branding: { ...settings.branding, primaryColor: e.target.value } })}
                  className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white w-32"
                  placeholder="#0891b2"
                />
              </div>
            </div>

            <button
              onClick={handleSave}
              disabled={saving}
              className="bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
            >
              {saving ? 'Saving…' : 'Save settings'}
            </button>

            {error && <p className="text-red-400 text-xs" role="alert">{error}</p>}
          </div>
        )}
      </div>
    </div>
  );
}
