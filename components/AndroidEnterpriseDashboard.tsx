import React, { useState, useEffect, useCallback } from 'react';
import { apiService } from '../services/apiService';

interface EnrollmentProfile {
  id: string;
  name: string;
  description: string;
  enrollment_mode: string;
  enrollment_url: string;
  enrollment_token: string;
  device_count: number;
  enabled: boolean;
  created_at: string;
}

interface KnoxStatus {
  configured: boolean;
  license_key_masked?: string;
  kme_enabled?: boolean;
  status?: string;
  activated_at?: string;
}

interface DedicatedConfig {
  profile_id: string;
  kiosk_app: string;
  kiosk_url: string;
  auto_launch: boolean;
  hide_status_bar: boolean;
  lock_task_mode: boolean;
  allowed_apps: string[];
}

const MODE_LABELS: Record<string, { label: string; color: string; desc: string }> = {
  work_profile: { label: 'Work Profile', color: 'bg-blue-900/50 text-blue-300', desc: 'Corporate data in isolated work profile' },
  fully_managed: { label: 'Fully Managed', color: 'bg-purple-900/50 text-purple-300', desc: 'Full device management for corporate-owned' },
  dedicated_device: { label: 'Dedicated Device', color: 'bg-orange-900/50 text-orange-300', desc: 'Single-purpose kiosk device' },
  corporate_owned_work_profile: { label: 'COPE', color: 'bg-teal-900/50 text-teal-300', desc: 'Corporate-owned, personal use enabled' },
};

export default function AndroidEnterpriseDashboard() {
  const [tab, setTab] = useState<'profiles' | 'knox' | 'dedicated'>('profiles');
  const [profiles, setProfiles] = useState<EnrollmentProfile[]>([]);
  const [knoxStatus, setKnoxStatus] = useState<KnoxStatus | null>(null);
  const [dedicatedConfigs, setDedicatedConfigs] = useState<DedicatedConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [selectedProfile, setSelectedProfile] = useState<EnrollmentProfile | null>(null);

  const [newProfile, setNewProfile] = useState({ name: '', description: '', enrollment_mode: 'work_profile' });
  const [knoxForm, setKnoxForm] = useState({ license_key: '', kme_enabled: false, kme_server: 'https://kme.samsungknox.com' });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [profs, knox, dedicated] = await Promise.all([
        apiService.get('/api/android-enterprise/profiles'),
        apiService.get('/api/android-enterprise/knox/status'),
        apiService.get('/api/android-enterprise/dedicated-device/configs'),
      ]);
      setProfiles(Array.isArray(profs) ? profs : []);
      setKnoxStatus(knox);
      setDedicatedConfigs(Array.isArray(dedicated) ? dedicated : []);
    } catch {
      // empty state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const createProfile = async () => {
    try {
      const created = await apiService.post('/api/android-enterprise/profiles', newProfile);
      setProfiles(prev => [created, ...prev]);
      setShowCreate(false);
      setNewProfile({ name: '', description: '', enrollment_mode: 'work_profile' });
    } catch { /* error */ }
  };

  const saveKnox = async () => {
    try {
      const result = await apiService.post('/api/android-enterprise/knox/license', knoxForm);
      setKnoxStatus({ ...result, configured: true });
    } catch { /* error */ }
  };

  const getEnrollmentUrl = async (profileId: string) => {
    try {
      const data = await apiService.get(`/api/android-enterprise/profiles/${profileId}/enrollment-url`);
      setSelectedProfile(profiles.find(p => p.id === profileId) || null);
      return data;
    } catch { return null; }
  };

  const MODES = Object.keys(MODE_LABELS);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Android Enterprise & Samsung Knox</h1>
          <p className="text-slate-400 text-sm mt-1">Enrollment profiles, Knox integration, and dedicated device management</p>
        </div>
        {tab === 'profiles' && (
          <button onClick={() => setShowCreate(true)} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm">
            + New Profile
          </button>
        )}
      </div>

      <div className="flex border border-slate-700 rounded-lg overflow-hidden w-fit">
        {(['profiles', 'knox', 'dedicated'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${tab === t ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-700'}`}
          >
            {t === 'profiles' ? 'Enrollment Profiles' : t === 'knox' ? 'Samsung Knox' : 'Dedicated Devices'}
          </button>
        ))}
      </div>

      {loading ? <div className="text-slate-400 text-center py-12">Loading...</div> : (
        <>
          {tab === 'profiles' && (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {profiles.length === 0 && <div className="col-span-full text-slate-400 text-center py-12">No enrollment profiles yet</div>}
              {profiles.map(profile => {
                const meta = MODE_LABELS[profile.enrollment_mode] || { label: profile.enrollment_mode, color: 'bg-slate-700 text-slate-300', desc: '' };
                return (
                  <div key={profile.id} className="bg-slate-800 rounded-xl border border-slate-700 p-5">
                    <div className="flex items-start justify-between mb-3">
                      <div>
                        <h3 className="text-white font-semibold">{profile.name}</h3>
                        <p className="text-slate-400 text-xs mt-0.5">{profile.description}</p>
                      </div>
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${meta.color}`}>{meta.label}</span>
                    </div>
                    <p className="text-slate-500 text-xs mb-3">{meta.desc}</p>
                    <div className="flex justify-between text-sm text-slate-400 mb-4">
                      <span>{profile.device_count} devices enrolled</span>
                      <span className={profile.enabled ? 'text-green-400' : 'text-slate-500'}>{profile.enabled ? 'Active' : 'Inactive'}</span>
                    </div>
                    <button
                      onClick={() => getEnrollmentUrl(profile.id)}
                      className="w-full py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm"
                    >
                      View Enrollment URL
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          {tab === 'knox' && (
            <div className="max-w-xl space-y-6">
              {knoxStatus?.configured ? (
                <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-3 h-3 rounded-full bg-green-400" />
                    <h3 className="text-white font-semibold">Knox License Active</h3>
                  </div>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between"><span className="text-slate-400">License Key</span><span className="text-slate-300 font-mono">{knoxStatus.license_key_masked}</span></div>
                    <div className="flex justify-between"><span className="text-slate-400">KME Enabled</span><span className="text-slate-300">{knoxStatus.kme_enabled ? 'Yes' : 'No'}</span></div>
                    <div className="flex justify-between"><span className="text-slate-400">Status</span><span className="text-green-400">{knoxStatus.status}</span></div>
                    <div className="flex justify-between"><span className="text-slate-400">Activated</span><span className="text-slate-300">{knoxStatus.activated_at?.slice(0, 10)}</span></div>
                  </div>
                </div>
              ) : null}
              <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
                <h3 className="text-white font-semibold mb-4">{knoxStatus?.configured ? 'Update Knox License' : 'Configure Knox License'}</h3>
                <div className="space-y-4">
                  <div>
                    <label className="text-slate-400 text-xs block mb-1">Knox License Key</label>
                    <input value={knoxForm.license_key} onChange={e => setKnoxForm(f => ({ ...f, license_key: e.target.value }))}
                      type="password" placeholder="Enter Knox license key"
                      className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm" />
                  </div>
                  <div>
                    <label className="text-slate-400 text-xs block mb-1">KME Server</label>
                    <input value={knoxForm.kme_server} onChange={e => setKnoxForm(f => ({ ...f, kme_server: e.target.value }))}
                      className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm" />
                  </div>
                  <label className="flex items-center gap-3 text-slate-300 text-sm cursor-pointer">
                    <input type="checkbox" checked={knoxForm.kme_enabled} onChange={e => setKnoxForm(f => ({ ...f, kme_enabled: e.target.checked }))} className="rounded" />
                    Enable Knox Mobile Enrollment (KME)
                  </label>
                  <button onClick={saveKnox} className="w-full py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm">
                    Save Knox Configuration
                  </button>
                </div>
              </div>
            </div>
          )}

          {tab === 'dedicated' && (
            <div className="space-y-4">
              {dedicatedConfigs.length === 0 ? (
                <div className="text-slate-400 text-center py-12">No dedicated device configurations. Create a Dedicated Device enrollment profile first.</div>
              ) : (
                dedicatedConfigs.map(config => (
                  <div key={config.profile_id} className="bg-slate-800 rounded-xl border border-slate-700 p-5">
                    <h3 className="text-white font-semibold mb-3">Profile: {config.profile_id}</h3>
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div><span className="text-slate-400">Kiosk App: </span><span className="text-slate-300">{config.kiosk_app || '—'}</span></div>
                      <div><span className="text-slate-400">Auto Launch: </span><span className="text-slate-300">{config.auto_launch ? 'Yes' : 'No'}</span></div>
                      <div><span className="text-slate-400">Lock Task Mode: </span><span className="text-slate-300">{config.lock_task_mode ? 'Yes' : 'No'}</span></div>
                      <div><span className="text-slate-400">Hide Status Bar: </span><span className="text-slate-300">{config.hide_status_bar ? 'Yes' : 'No'}</span></div>
                      <div className="col-span-2"><span className="text-slate-400">Allowed Apps: </span><span className="text-slate-300">{config.allowed_apps?.join(', ') || 'None'}</span></div>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </>
      )}

      {showCreate && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 w-full max-w-md">
            <h2 className="text-white font-bold text-lg mb-4">New Enrollment Profile</h2>
            <div className="space-y-4">
              <input value={newProfile.name} onChange={e => setNewProfile(p => ({ ...p, name: e.target.value }))}
                placeholder="Profile name" className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm" />
              <input value={newProfile.description} onChange={e => setNewProfile(p => ({ ...p, description: e.target.value }))}
                placeholder="Description (optional)" className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm" />
              <div>
                <label className="text-slate-400 text-xs block mb-2">Enrollment Mode</label>
                <div className="space-y-2">
                  {MODES.map(mode => (
                    <label key={mode} className="flex items-start gap-3 cursor-pointer p-3 rounded-lg border transition-colors"
                      style={{ borderColor: newProfile.enrollment_mode === mode ? '#3b82f6' : '#334155', background: newProfile.enrollment_mode === mode ? 'rgba(59,130,246,0.1)' : 'transparent' }}>
                      <input type="radio" name="mode" value={mode} checked={newProfile.enrollment_mode === mode}
                        onChange={() => setNewProfile(p => ({ ...p, enrollment_mode: mode }))} className="mt-0.5" />
                      <div>
                        <div className="text-white text-sm font-medium">{MODE_LABELS[mode].label}</div>
                        <div className="text-slate-400 text-xs">{MODE_LABELS[mode].desc}</div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button onClick={createProfile} className="flex-1 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm">Create</button>
              <button onClick={() => setShowCreate(false)} className="flex-1 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
