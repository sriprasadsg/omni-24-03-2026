import React, { useEffect, useState } from 'react';
import { getGeoSecuritySettings, setGeoSecuritySettings, GeoSecuritySettings } from '../services/apiService';
import { showToast } from '../utils/toast';

// Admin-gated Security settings panel (D-06, GSEC-03). Distinct from Phase
// 46's PrivacyDashboard — security detector config lives here, not folded
// into privacy config. Drives the Plan 47-04 /settings/geo-security
// GET/PATCH endpoints: impossible-travel + geo-fence toggles, plus the
// per-tenant allowed-country-code (ISO 3166 alpha-2) allowlist.
const DEFAULT_SETTINGS: GeoSecuritySettings = {
  impossible_travel_enabled: true,
  geo_fence_enabled: false,
  allowed_country_codes: [],
};

export function SecuritySettingsDashboard() {
  const [settings, setSettings] = useState<GeoSecuritySettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [newCode, setNewCode] = useState('');

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const s = await getGeoSecuritySettings();
      setSettings(s);
    } catch (e: any) {
      showToast(e?.message || 'Failed to load geo-security settings', 'error');
    } finally {
      setLoading(false);
    }
  }

  async function persist(update: Partial<GeoSecuritySettings>, successMessage: string) {
    setBusy(true);
    try {
      const next = await setGeoSecuritySettings(update);
      setSettings(next);
      showToast(successMessage, 'success');
    } catch (e: any) {
      showToast(e?.message || 'Failed to update geo-security settings', 'error');
    } finally {
      setBusy(false);
    }
  }

  function toggleImpossibleTravel() {
    const next = !settings.impossible_travel_enabled;
    persist({ impossible_travel_enabled: next }, next ? 'Impossible-travel detection enabled' : 'Impossible-travel detection disabled');
  }

  function toggleGeoFence() {
    const next = !settings.geo_fence_enabled;
    persist({ geo_fence_enabled: next }, next ? 'Geo-fence detection enabled' : 'Geo-fence detection disabled');
  }

  function addCountryCode() {
    const code = newCode.trim().toUpperCase();
    if (!code) return;
    if (code.length !== 2 || !/^[A-Z]{2}$/.test(code)) {
      showToast('Enter a valid ISO 3166 alpha-2 country code (e.g. US, GB)', 'error');
      return;
    }
    if (settings.allowed_country_codes.includes(code)) {
      setNewCode('');
      return;
    }
    const next = [...settings.allowed_country_codes, code];
    setNewCode('');
    persist({ allowed_country_codes: next }, `Added ${code} to the allowed-region allowlist`);
  }

  function removeCountryCode(code: string) {
    const next = settings.allowed_country_codes.filter((c) => c !== code);
    persist({ allowed_country_codes: next }, `Removed ${code} from the allowed-region allowlist`);
  }

  if (loading) {
    return (
      <div className="p-6 bg-gray-900 min-h-screen text-white">
        <p className="text-gray-400 text-sm">Loading security settings…</p>
      </div>
    );
  }

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Security Settings</h1>
        <p className="text-gray-400 text-sm mt-1">
          Agent-scoped geo security detectors — alert-only, never connection-blocking.
        </p>
      </div>

      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 mb-4">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex-1 min-w-[240px]">
            <h2 className="font-medium text-sm">Impossible-Travel Detection</h2>
            <p className="text-gray-400 text-xs mt-1">
              Flags an agent whose two most-recent check-ins imply travel faster than commercial-flight
              speed (~1000 km/h). Suppressed automatically when either check-in carries a VPN/hosting
              heuristic flag, to avoid corporate-VPN false positives. Alert-only — no connection impact.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={settings.impossible_travel_enabled}
            aria-label={settings.impossible_travel_enabled ? 'Disable impossible-travel detection' : 'Enable impossible-travel detection'}
            disabled={busy}
            onClick={toggleImpossibleTravel}
            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors disabled:opacity-50 ${settings.impossible_travel_enabled ? 'bg-blue-600' : 'bg-gray-600'}`}
          >
            <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${settings.impossible_travel_enabled ? 'translate-x-5' : 'translate-x-1'}`} />
          </button>
        </div>
      </div>

      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 mb-4">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex-1 min-w-[240px]">
            <h2 className="font-medium text-sm">Geo-Fence Detection</h2>
            <p className="text-gray-400 text-xs mt-1">
              Alert-only (no blocking or quarantine) — a check-in from a country outside the allowed-region
              allowlist below raises an alert. Enable this only after populating the allowlist; an empty
              allowlist means every country will be flagged.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={settings.geo_fence_enabled}
            aria-label={settings.geo_fence_enabled ? 'Disable geo-fence detection' : 'Enable geo-fence detection'}
            disabled={busy}
            onClick={toggleGeoFence}
            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors disabled:opacity-50 ${settings.geo_fence_enabled ? 'bg-blue-600' : 'bg-gray-600'}`}
          >
            <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${settings.geo_fence_enabled ? 'translate-x-5' : 'translate-x-1'}`} />
          </button>
        </div>
      </div>

      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
        <h2 className="font-medium text-sm mb-1">Allowed Regions</h2>
        <p className="text-gray-400 text-xs mb-3">
          ISO 3166 alpha-2 country-code allowlist checked by geo-fence detection. Add the countries your
          agents are expected to check in from.
        </p>
        <div className="flex flex-wrap gap-2 mb-3">
          {settings.allowed_country_codes.length === 0 && (
            <span className="text-gray-500 text-xs italic">No countries allowed yet.</span>
          )}
          {settings.allowed_country_codes.map((code) => (
            <span
              key={code}
              className="inline-flex items-center gap-1.5 bg-gray-700 border border-gray-600 rounded-full px-3 py-1 text-xs"
            >
              {code}
              <button
                type="button"
                aria-label={`Remove ${code} from allowed regions`}
                disabled={busy}
                onClick={() => removeCountryCode(code)}
                className="text-gray-400 hover:text-red-400 disabled:opacity-50"
              >
                ×
              </button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={newCode}
            onChange={(e) => setNewCode(e.target.value.toUpperCase())}
            onKeyDown={(e) => { if (e.key === 'Enter') addCountryCode(); }}
            maxLength={2}
            placeholder="e.g. US"
            aria-label="Add country code"
            className="bg-gray-900 border border-gray-600 rounded-lg px-3 py-1.5 text-sm w-24 uppercase"
          />
          <button
            type="button"
            onClick={addCountryCode}
            disabled={busy}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-4 py-1.5 rounded-lg text-sm font-medium"
          >
            + Add
          </button>
        </div>
      </div>
    </div>
  );
}
