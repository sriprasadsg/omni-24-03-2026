import React, { useState, useEffect, useCallback } from 'react';
import { apiService } from '../services/apiService';

interface ProfileType {
  type: string;
  label: string;
  platforms: string[];
}

interface ConfigProfile {
  id: string;
  name: string;
  description: string;
  profile_type: string;
  platforms: string[];
  settings: Record<string, unknown>;
  assigned_groups: string[];
  assigned_devices: string[];
  enabled: boolean;
  created_at: string;
}

const TYPE_BADGE: Record<string, string> = {
  browser: 'bg-blue-900/50 text-blue-300 border border-blue-700',
  usb: 'bg-orange-900/50 text-orange-300 border border-orange-700',
  wifi: 'bg-green-900/50 text-green-300 border border-green-700',
  vpn: 'bg-purple-900/50 text-purple-300 border border-purple-700',
  kiosk: 'bg-teal-900/50 text-teal-300 border border-teal-700',
};

const TYPE_LABELS: Record<string, string> = {
  browser: 'Browser', usb: 'USB Control', wifi: 'Wi-Fi', vpn: 'VPN', kiosk: 'Kiosk',
};

function SettingsSummary({ type, settings }: { type: string; settings: Record<string, unknown> }) {
  const items: string[] = [];
  if (type === 'browser') {
    if (settings.homepage) items.push(`Homepage: ${settings.homepage}`);
    if (settings.force_safe_search) items.push('Safe search enforced');
    if ((settings.blocked_urls as string[])?.length) items.push(`${(settings.blocked_urls as string[]).length} blocked URLs`);
  } else if (type === 'usb') {
    if (settings.block_mass_storage) items.push('Mass storage blocked');
    if (settings.block_removable_media) items.push('Removable media blocked');
    if (settings.read_only_mode) items.push('Read-only mode');
  } else if (type === 'wifi') {
    if (settings.ssid) items.push(`SSID: ${settings.ssid}`);
    if (settings.security_type) items.push(`Security: ${settings.security_type}`);
    if (settings.auto_connect) items.push('Auto-connect');
  } else if (type === 'vpn') {
    if (settings.vpn_type) items.push(`Type: ${settings.vpn_type}`);
    if (settings.server_address) items.push(`Server: ${settings.server_address}`);
    if (settings.always_on) items.push('Always-on VPN');
  } else if (type === 'kiosk') {
    if (settings.kiosk_mode) items.push(`Mode: ${settings.kiosk_mode}`);
    if (settings.auto_launch_app) items.push(`Launch: ${settings.auto_launch_app}`);
    if ((settings.allowed_apps as string[])?.length) items.push(`${(settings.allowed_apps as string[]).length} allowed apps`);
  }
  return (
    <div className="space-y-1">
      {items.map((item, i) => <div key={i} className="text-slate-400 text-xs">{item}</div>)}
      {items.length === 0 && <div className="text-slate-500 text-xs">No settings configured</div>}
    </div>
  );
}

function BrowserForm({ settings, onChange }: { settings: Record<string, unknown>; onChange: (s: Record<string, unknown>) => void }) {
  return (
    <div className="space-y-3">
      <input value={(settings.homepage as string) || ''} onChange={e => onChange({ ...settings, homepage: e.target.value })}
        placeholder="Homepage URL" className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm" />
      <label className="flex items-center gap-2 text-slate-300 text-sm cursor-pointer">
        <input type="checkbox" checked={!!settings.force_safe_search} onChange={e => onChange({ ...settings, force_safe_search: e.target.checked })} />
        Force Safe Search
      </label>
      <label className="flex items-center gap-2 text-slate-300 text-sm cursor-pointer">
        <input type="checkbox" checked={!!settings.block_incognito} onChange={e => onChange({ ...settings, block_incognito: e.target.checked })} />
        Block Incognito Mode
      </label>
    </div>
  );
}

function UsbForm({ settings, onChange }: { settings: Record<string, unknown>; onChange: (s: Record<string, unknown>) => void }) {
  return (
    <div className="space-y-3">
      {[['block_mass_storage', 'Block Mass Storage Devices'], ['block_removable_media', 'Block Removable Media'], ['read_only_mode', 'Read-Only Mode (allow reads, block writes)']].map(([key, label]) => (
        <label key={key} className="flex items-center gap-2 text-slate-300 text-sm cursor-pointer">
          <input type="checkbox" checked={!!settings[key]} onChange={e => onChange({ ...settings, [key]: e.target.checked })} />
          {label}
        </label>
      ))}
    </div>
  );
}

function WifiForm({ settings, onChange }: { settings: Record<string, unknown>; onChange: (s: Record<string, unknown>) => void }) {
  return (
    <div className="space-y-3">
      <input value={(settings.ssid as string) || ''} onChange={e => onChange({ ...settings, ssid: e.target.value })}
        placeholder="Network SSID" className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm" />
      <select value={(settings.security_type as string) || 'WPA2'} onChange={e => onChange({ ...settings, security_type: e.target.value })}
        className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm">
        {['Open', 'WEP', 'WPA2', 'WPA3', 'WPA2-Enterprise', 'WPA3-Enterprise'].map(s => <option key={s} value={s}>{s}</option>)}
      </select>
      <input type="password" value={(settings.passphrase as string) || ''} onChange={e => onChange({ ...settings, passphrase: e.target.value })}
        placeholder="Passphrase (leave empty for EAP)" className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm" />
      <label className="flex items-center gap-2 text-slate-300 text-sm cursor-pointer">
        <input type="checkbox" checked={!!settings.auto_connect} onChange={e => onChange({ ...settings, auto_connect: e.target.checked })} />
        Auto-connect
      </label>
    </div>
  );
}

function VpnForm({ settings, onChange }: { settings: Record<string, unknown>; onChange: (s: Record<string, unknown>) => void }) {
  return (
    <div className="space-y-3">
      <select value={(settings.vpn_type as string) || 'IKEv2'} onChange={e => onChange({ ...settings, vpn_type: e.target.value })}
        className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm">
        {['IKEv2', 'SSL/TLS', 'L2TP/IPSec', 'PPTP', 'WireGuard'].map(s => <option key={s} value={s}>{s}</option>)}
      </select>
      <input value={(settings.server_address as string) || ''} onChange={e => onChange({ ...settings, server_address: e.target.value })}
        placeholder="VPN Server Address" className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm" />
      <select value={(settings.auth_type as string) || 'password'} onChange={e => onChange({ ...settings, auth_type: e.target.value })}
        className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm">
        {['password', 'certificate', 'mfa'].map(s => <option key={s} value={s}>{s}</option>)}
      </select>
      {[['always_on', 'Always-on VPN'], ['per_app_vpn', 'Per-App VPN'], ['split_tunneling', 'Split Tunneling']].map(([key, label]) => (
        <label key={key} className="flex items-center gap-2 text-slate-300 text-sm cursor-pointer">
          <input type="checkbox" checked={!!settings[key]} onChange={e => onChange({ ...settings, [key]: e.target.checked })} />
          {label}
        </label>
      ))}
    </div>
  );
}

function KioskForm({ settings, onChange }: { settings: Record<string, unknown>; onChange: (s: Record<string, unknown>) => void }) {
  return (
    <div className="space-y-3">
      <select value={(settings.kiosk_mode as string) || 'single_app'} onChange={e => onChange({ ...settings, kiosk_mode: e.target.value })}
        className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm">
        {[['single_app', 'Single App'], ['multi_app', 'Multi-App'], ['browser', 'Browser Kiosk']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
      <input value={(settings.auto_launch_app as string) || ''} onChange={e => onChange({ ...settings, auto_launch_app: e.target.value })}
        placeholder="Auto-launch app (bundle ID)" className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm" />
      {[['show_status_bar', 'Show Status Bar'], ['show_navigation_bar', 'Show Navigation Bar'], ['allow_settings', 'Allow Settings Access']].map(([key, label]) => (
        <label key={key} className="flex items-center gap-2 text-slate-300 text-sm cursor-pointer">
          <input type="checkbox" checked={!!settings[key]} onChange={e => onChange({ ...settings, [key]: e.target.checked })} />
          {label}
        </label>
      ))}
    </div>
  );
}

const SETTINGS_FORM: Record<string, React.ComponentType<{ settings: Record<string, unknown>; onChange: (s: Record<string, unknown>) => void }>> = {
  browser: BrowserForm, usb: UsbForm, wifi: WifiForm, vpn: VpnForm, kiosk: KioskForm,
};

export default function DeviceConfigProfilesDashboard() {
  const [profiles, setProfiles] = useState<ConfigProfile[]>([]);
  const [profileTypes, setProfileTypes] = useState<ProfileType[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterType, setFilterType] = useState<string>('all');
  const [showCreate, setShowCreate] = useState(false);
  const [newProfile, setNewProfile] = useState({ name: '', description: '', profile_type: 'wifi', platforms: [] as string[], settings: {} as Record<string, unknown> });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [profs, types] = await Promise.all([
        apiService.get('/api/device-config-profiles'),
        apiService.get('/api/device-config-profiles/types'),
      ]);
      setProfiles(Array.isArray(profs) ? profs : []);
      setProfileTypes(Array.isArray(types) ? types : []);
    } catch {
      // empty state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const createProfile = async () => {
    try {
      const created = await apiService.post('/api/device-config-profiles', newProfile);
      setProfiles(prev => [created, ...prev]);
      setShowCreate(false);
      setNewProfile({ name: '', description: '', profile_type: 'wifi', platforms: [], settings: {} });
    } catch { /* error */ }
  };

  const filtered = filterType === 'all' ? profiles : profiles.filter(p => p.profile_type === filterType);
  const SettingsFormComponent = SETTINGS_FORM[newProfile.profile_type];
  const PLATFORMS = ['windows', 'macos', 'ios', 'android', 'linux'];

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Device Configuration Profiles</h1>
          <p className="text-slate-400 text-sm mt-1">Browser, USB, Wi-Fi, VPN, and Kiosk profiles for managed devices</p>
        </div>
        <button onClick={() => setShowCreate(true)} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm">
          + New Profile
        </button>
      </div>

      <div className="flex gap-2 flex-wrap">
        {['all', ...Object.keys(TYPE_LABELS)].map(t => (
          <button
            key={t}
            onClick={() => setFilterType(t)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${filterType === t ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700'}`}
          >
            {t === 'all' ? `All (${profiles.length})` : TYPE_LABELS[t]}
          </button>
        ))}
      </div>

      {loading ? <div className="text-slate-400 text-center py-12">Loading...</div> : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.length === 0 && <div className="col-span-full text-slate-400 text-center py-12">No configuration profiles yet</div>}
          {filtered.map(profile => (
            <div key={profile.id} className="bg-slate-800 rounded-xl border border-slate-700 p-5">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="text-white font-semibold">{profile.name}</h3>
                  <p className="text-slate-400 text-xs mt-0.5">{profile.description}</p>
                </div>
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${TYPE_BADGE[profile.profile_type] || 'bg-slate-700 text-slate-300'}`}>
                  {TYPE_LABELS[profile.profile_type] || profile.profile_type}
                </span>
              </div>
              <SettingsSummary type={profile.profile_type} settings={profile.settings} />
              <div className="mt-3 pt-3 border-t border-slate-700 flex justify-between text-xs text-slate-500">
                <span>{profile.platforms.join(', ') || 'All platforms'}</span>
                <span>{(profile.assigned_groups.length + profile.assigned_devices.length)} assigned</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 overflow-y-auto py-8">
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 w-full max-w-lg my-auto">
            <h2 className="text-white font-bold text-lg mb-4">New Configuration Profile</h2>
            <div className="space-y-4">
              <input value={newProfile.name} onChange={e => setNewProfile(p => ({ ...p, name: e.target.value }))}
                placeholder="Profile name" className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm" />
              <input value={newProfile.description} onChange={e => setNewProfile(p => ({ ...p, description: e.target.value }))}
                placeholder="Description (optional)" className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm" />
              <div>
                <label className="text-slate-400 text-xs block mb-2">Profile Type</label>
                <div className="grid grid-cols-3 gap-2">
                  {Object.entries(TYPE_LABELS).map(([type, label]) => (
                    <button
                      key={type}
                      onClick={() => setNewProfile(p => ({ ...p, profile_type: type, settings: {} }))}
                      className={`px-3 py-2 rounded-lg text-sm border transition-colors ${newProfile.profile_type === type ? 'border-blue-500 bg-blue-900/30 text-blue-300' : 'border-slate-600 text-slate-400 hover:border-slate-500'}`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-slate-400 text-xs block mb-2">Target Platforms</label>
                <div className="flex flex-wrap gap-2">
                  {PLATFORMS.map(pl => (
                    <label key={pl} className="flex items-center gap-1.5 text-slate-300 text-sm cursor-pointer">
                      <input type="checkbox"
                        checked={newProfile.platforms.includes(pl)}
                        onChange={e => setNewProfile(p => ({ ...p, platforms: e.target.checked ? [...p.platforms, pl] : p.platforms.filter(x => x !== pl) }))}
                      />
                      {pl}
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-slate-400 text-xs block mb-2">Settings</label>
                {SettingsFormComponent && <SettingsFormComponent settings={newProfile.settings} onChange={s => setNewProfile(p => ({ ...p, settings: s }))} />}
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button onClick={createProfile} className="flex-1 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm">Create Profile</button>
              <button onClick={() => setShowCreate(false)} className="flex-1 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
