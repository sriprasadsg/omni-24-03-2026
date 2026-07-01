import React, { useState, useEffect, useRef } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

interface AutopilotDevice {
  id: string;
  serial_number: string;
  hardware_hash: string;
  manufacturer: string;
  model: string;
  group_tag: string;
  assigned_user: string;
  profile_id: string | null;
  status: string;
  esp_stage: string | null;
  esp_progress: number;
  esp_error: string | null;
  last_contact: string | null;
  enrolled_at: string | null;
  registered_at: string;
  notes: string;
}

interface AutopilotProfile {
  id: string;
  name: string;
  description: string;
  profile_type: string;
  deployment_mode: string;
  hide_privacy_settings: boolean;
  hide_eula: boolean;
  auto_enroll_mdm: boolean;
  apply_device_name_template: string;
  allowed_group: string;
  assigned_devices_count: number;
  created_at: string;
}

interface Summary {
  total_devices: number;
  enrolled: number;
  deploying: number;
  failed: number;
  registered: number;
  total_profiles: number;
}

const STATUS_STYLES: Record<string, string> = {
  registered: 'bg-slate-700 text-slate-300',
  assigned: 'bg-blue-900/40 text-blue-300',
  deploying: 'bg-yellow-900/40 text-yellow-300',
  enrolled: 'bg-green-900/40 text-green-300',
  failed: 'bg-red-900/40 text-red-300',
  deregistered: 'bg-gray-800 text-gray-500',
};

const ESP_STAGE_LABELS: Record<string, string> = {
  device_preparation: 'Device Preparation',
  device_setup: 'Device Setup',
  account_setup: 'Account Setup',
  completed: 'Completed',
  failed: 'Failed',
};

const BLANK_PROFILE = {
  name: '', description: '', profile_type: 'user_driven', deployment_mode: 'azure_ad_join',
  hide_privacy_settings: true, hide_eula: true, auto_enroll_mdm: true,
  apply_device_name_template: '', allowed_group: '',
};

export default function AutopilotDashboard() {
  const [tab, setTab] = useState<'devices' | 'profiles' | 'esp'>('devices');
  const [devices, setDevices] = useState<AutopilotDevice[]>([]);
  const [profiles, setProfiles] = useState<AutopilotProfile[]>([]);
  const [espEvents, setEspEvents] = useState<any[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [showAddDevice, setShowAddDevice] = useState(false);
  const [showAddProfile, setShowAddProfile] = useState(false);
  const [editProfile, setEditProfile] = useState<AutopilotProfile | null>(null);
  const [deviceForm, setDeviceForm] = useState({ serial_number: '', manufacturer: '', model: '', group_tag: '', assigned_user: '', notes: '' });
  const [profileForm, setProfileForm] = useState({ ...BLANK_PROFILE });
  const [saving, setSaving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => { loadAll(); }, []);
  useEffect(() => { if (tab === 'esp') loadEsp(); }, [tab]);

  async function loadAll() {
    try {
      const [dRes, pRes, sRes] = await Promise.all([
        authFetch('/api/autopilot/devices'),
        authFetch('/api/autopilot/profiles'),
        authFetch('/api/autopilot/summary'),
      ]);
      const [d, p, s] = await Promise.all([dRes.json(), pRes.json(), sRes.json()]);
      setDevices(d.devices || []);
      setProfiles(p.profiles || []);
      setSummary(s);
    } catch (e) { console.error(e); }
  }

  async function loadEsp() {
    try {
      const r = await authFetch('/api/autopilot/esp/events');
      const d = await r.json();
      setEspEvents(d.events || []);
    } catch (e) { console.error(e); }
  }

  async function addDevice() {
    setSaving(true);
    try {
      const r = await authFetch('/api/autopilot/devices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(deviceForm),
      });
      if (r.ok) {
        showToast('Device registered', 'success');
        setShowAddDevice(false);
        setDeviceForm({ serial_number: '', manufacturer: '', model: '', group_tag: '', assigned_user: '', notes: '' });
        loadAll();
      } else {
        const d = await r.json();
        showToast(d.detail || 'Failed', 'error');
      }
    } finally { setSaving(false); }
  }

  async function deleteDevice(id: string) {
    if (!confirm('Deregister this device from Autopilot?')) return;
    const r = await authFetch(`/api/autopilot/devices/${id}`, { method: 'DELETE' });
    if (r.ok) { showToast('Device deregistered', 'success'); loadAll(); }
  }

  async function saveProfile() {
    setSaving(true);
    try {
      const url = editProfile ? `/api/autopilot/profiles/${editProfile.id}` : '/api/autopilot/profiles';
      const method = editProfile ? 'PATCH' : 'POST';
      const r = await authFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(profileForm),
      });
      if (r.ok) {
        showToast(editProfile ? 'Profile updated' : 'Profile created', 'success');
        setShowAddProfile(false);
        setEditProfile(null);
        setProfileForm({ ...BLANK_PROFILE });
        loadAll();
      } else {
        const d = await r.json();
        showToast(d.detail || 'Failed', 'error');
      }
    } finally { setSaving(false); }
  }

  async function deleteProfile(id: string) {
    if (!confirm('Delete this deployment profile?')) return;
    const r = await authFetch(`/api/autopilot/profiles/${id}`, { method: 'DELETE' });
    if (r.ok) { showToast('Profile deleted', 'success'); loadAll(); }
    else { const d = await r.json(); showToast(d.detail || 'Cannot delete', 'error'); }
  }

  async function importCsv(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    const r = await authFetch('/api/autopilot/devices/import', { method: 'POST', body: fd });
    const d = await r.json();
    showToast(`Imported ${d.imported}, skipped ${d.skipped}`, r.ok ? 'success' : 'error');
    if (r.ok) loadAll();
    if (fileRef.current) fileRef.current.value = '';
  }

  function openEditProfile(p: AutopilotProfile) {
    setEditProfile(p);
    setProfileForm({
      name: p.name, description: p.description, profile_type: p.profile_type,
      deployment_mode: p.deployment_mode, hide_privacy_settings: p.hide_privacy_settings,
      hide_eula: p.hide_eula, auto_enroll_mdm: p.auto_enroll_mdm,
      apply_device_name_template: p.apply_device_name_template, allowed_group: p.allowed_group,
    });
    setShowAddProfile(true);
  }

  const filteredDevices = statusFilter === 'all' ? devices : devices.filter(d => d.status === statusFilter);
  const profileMap = Object.fromEntries(profiles.map(p => [p.id, p.name]));

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="flex justify-between items-start mb-6">
        <div>
          <h1 className="text-2xl font-bold">Windows Autopilot</h1>
          <p className="text-gray-400 text-sm mt-1">Zero-touch device provisioning, deployment profiles, and enrollment status</p>
        </div>
        <div className="flex gap-2">
          <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={importCsv} />
          <button onClick={() => fileRef.current?.click()} className="px-3 py-2 text-sm bg-slate-700 hover:bg-slate-600 rounded-lg">
            Import CSV
          </button>
          <button onClick={() => { setShowAddProfile(true); setEditProfile(null); setProfileForm({ ...BLANK_PROFILE }); }}
            className="px-3 py-2 text-sm bg-blue-700 hover:bg-blue-600 rounded-lg">
            + New Profile
          </button>
          <button onClick={() => setShowAddDevice(true)} className="px-3 py-2 text-sm bg-indigo-700 hover:bg-indigo-600 rounded-lg">
            + Register Device
          </button>
        </div>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-6">
          {[
            { label: 'Total Devices', value: summary.total_devices, color: 'text-white' },
            { label: 'Enrolled', value: summary.enrolled, color: 'text-green-400' },
            { label: 'Deploying', value: summary.deploying, color: 'text-yellow-400' },
            { label: 'Failed', value: summary.failed, color: 'text-red-400' },
            { label: 'Registered', value: summary.registered, color: 'text-slate-400' },
            { label: 'Profiles', value: summary.total_profiles, color: 'text-blue-400' },
          ].map(c => (
            <div key={c.label} className="bg-gray-800 rounded-lg p-4 text-center">
              <div className={`text-2xl font-bold ${c.color}`}>{c.value}</div>
              <div className="text-xs text-gray-400 mt-1">{c.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-4 border-b border-gray-700">
        {(['devices', 'profiles', 'esp'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize ${tab === t ? 'border-b-2 border-blue-500 text-blue-400' : 'text-gray-400 hover:text-white'}`}>
            {t === 'esp' ? 'ESP Monitor' : t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {/* Devices tab */}
      {tab === 'devices' && (
        <>
          <div className="flex gap-2 mb-3 flex-wrap">
            {['all', 'registered', 'assigned', 'deploying', 'enrolled', 'failed'].map(s => (
              <button key={s} onClick={() => setStatusFilter(s)}
                className={`px-3 py-1 text-xs rounded-full capitalize ${statusFilter === s ? 'bg-blue-700 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
                {s}
              </button>
            ))}
          </div>
          <div className="bg-gray-800 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-700/50 text-gray-400 text-xs uppercase">
                <tr>
                  <th className="px-4 py-3 text-left">Serial Number</th>
                  <th className="px-4 py-3 text-left">Device</th>
                  <th className="px-4 py-3 text-left">Status</th>
                  <th className="px-4 py-3 text-left">Profile</th>
                  <th className="px-4 py-3 text-left">Assigned User</th>
                  <th className="px-4 py-3 text-left">Registered</th>
                  <th className="px-4 py-3 text-left">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {filteredDevices.length === 0 && (
                  <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500">No devices found</td></tr>
                )}
                {filteredDevices.map(d => (
                  <tr key={d.id} className="hover:bg-gray-700/30">
                    <td className="px-4 py-3 font-mono text-xs">{d.serial_number}</td>
                    <td className="px-4 py-3">
                      <div className="text-white">{d.model || '—'}</div>
                      <div className="text-gray-500 text-xs">{d.manufacturer}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs capitalize ${STATUS_STYLES[d.status] || 'bg-gray-700 text-gray-300'}`}>
                        {d.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-300 text-xs">{d.profile_id ? (profileMap[d.profile_id] || 'Unknown') : '—'}</td>
                    <td className="px-4 py-3 text-gray-300 text-xs">{d.assigned_user || '—'}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{d.registered_at ? new Date(d.registered_at).toLocaleDateString() : '—'}</td>
                    <td className="px-4 py-3">
                      <button onClick={() => deleteDevice(d.id)} className="text-red-400 hover:text-red-300 text-xs">Remove</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Profiles tab */}
      {tab === 'profiles' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {profiles.length === 0 && (
            <div className="col-span-3 text-center text-gray-500 py-12">No deployment profiles yet</div>
          )}
          {profiles.map(p => (
            <div key={p.id} className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <div className="flex justify-between items-start">
                <div>
                  <h3 className="font-medium text-white">{p.name}</h3>
                  <p className="text-gray-400 text-xs mt-1">{p.description || 'No description'}</p>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => openEditProfile(p)} className="text-blue-400 hover:text-blue-300 text-xs">Edit</button>
                  <button onClick={() => deleteProfile(p.id)} className="text-red-400 hover:text-red-300 text-xs">Delete</button>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-gray-400">
                <div><span className="text-gray-500">Type:</span> <span className="text-gray-300 capitalize">{p.profile_type.replace(/_/g, ' ')}</span></div>
                <div><span className="text-gray-500">Mode:</span> <span className="text-gray-300 capitalize">{p.deployment_mode.replace(/_/g, ' ')}</span></div>
                <div><span className="text-gray-500">MDM:</span> <span className={p.auto_enroll_mdm ? 'text-green-400' : 'text-gray-400'}>{p.auto_enroll_mdm ? 'Auto' : 'Manual'}</span></div>
                <div><span className="text-gray-500">Devices:</span> <span className="text-white font-medium">{p.assigned_devices_count}</span></div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ESP Monitor tab */}
      {tab === 'esp' && (
        <div className="bg-gray-800 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-700/50 text-gray-400 text-xs uppercase">
              <tr>
                <th className="px-4 py-3 text-left">Device</th>
                <th className="px-4 py-3 text-left">ESP Stage</th>
                <th className="px-4 py-3 text-left">Progress</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Last Contact</th>
                <th className="px-4 py-3 text-left">Enrolled</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {espEvents.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500">No enrollment events yet</td></tr>
              )}
              {espEvents.map(e => (
                <tr key={e.id} className="hover:bg-gray-700/30">
                  <td className="px-4 py-3">
                    <div className="text-white text-xs font-mono">{e.serial_number}</div>
                    <div className="text-gray-500 text-xs">{e.manufacturer} {e.model}</div>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-300">{ESP_STAGE_LABELS[e.esp_stage] || e.esp_stage}</td>
                  <td className="px-4 py-3">
                    <div className="w-32 bg-gray-700 rounded-full h-2">
                      <div className={`h-2 rounded-full ${e.esp_stage === 'failed' ? 'bg-red-500' : 'bg-blue-500'}`}
                        style={{ width: `${e.esp_progress}%` }} />
                    </div>
                    <span className="text-xs text-gray-400 mt-0.5 block">{e.esp_progress}%</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs capitalize ${STATUS_STYLES[e.status] || 'bg-gray-700 text-gray-300'}`}>
                      {e.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-400">{e.last_contact ? new Date(e.last_contact).toLocaleString() : '—'}</td>
                  <td className="px-4 py-3 text-xs text-gray-400">{e.enrolled_at ? new Date(e.enrolled_at).toLocaleString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Add Device Modal */}
      {showAddDevice && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-xl p-6 w-full max-w-md border border-gray-700">
            <h2 className="text-lg font-semibold mb-4">Register Device</h2>
            <div className="space-y-3">
              {[
                { key: 'serial_number', label: 'Serial Number *', placeholder: 'e.g. ABC1234XYZ' },
                { key: 'manufacturer', label: 'Manufacturer', placeholder: 'e.g. Dell' },
                { key: 'model', label: 'Model', placeholder: 'e.g. Latitude 5540' },
                { key: 'group_tag', label: 'Group Tag', placeholder: 'e.g. Sales-Devices' },
                { key: 'assigned_user', label: 'Assigned User (UPN)', placeholder: 'user@company.com' },
                { key: 'notes', label: 'Notes', placeholder: 'Optional notes' },
              ].map(f => (
                <div key={f.key}>
                  <label className="text-xs text-gray-400 block mb-1">{f.label}</label>
                  <input value={(deviceForm as any)[f.key]} onChange={e => setDeviceForm(p => ({ ...p, [f.key]: e.target.value }))}
                    placeholder={f.placeholder}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
                </div>
              ))}
            </div>
            <div className="flex gap-2 mt-4 justify-end">
              <button onClick={() => setShowAddDevice(false)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">Cancel</button>
              <button onClick={addDevice} disabled={saving || !deviceForm.serial_number}
                className="px-4 py-2 text-sm bg-indigo-700 hover:bg-indigo-600 rounded-lg disabled:opacity-50">
                {saving ? 'Saving…' : 'Register'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add/Edit Profile Modal */}
      {showAddProfile && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-xl p-6 w-full max-w-lg border border-gray-700 max-h-[90vh] overflow-y-auto">
            <h2 className="text-lg font-semibold mb-4">{editProfile ? 'Edit Profile' : 'New Deployment Profile'}</h2>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-400 block mb-1">Profile Name *</label>
                <input value={profileForm.name} onChange={e => setProfileForm(p => ({ ...p, name: e.target.value }))}
                  placeholder="e.g. Standard Employee Deployment"
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Description</label>
                <input value={profileForm.description} onChange={e => setProfileForm(p => ({ ...p, description: e.target.value }))}
                  placeholder="Optional description"
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Profile Type</label>
                  <select value={profileForm.profile_type} onChange={e => setProfileForm(p => ({ ...p, profile_type: e.target.value }))}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500">
                    <option value="user_driven">User Driven</option>
                    <option value="self_deploying">Self Deploying</option>
                    <option value="pre_provisioning">Pre-Provisioning</option>
                    <option value="white_glove">White Glove</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Deployment Mode</label>
                  <select value={profileForm.deployment_mode} onChange={e => setProfileForm(p => ({ ...p, deployment_mode: e.target.value }))}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500">
                    <option value="azure_ad_join">Azure AD Join</option>
                    <option value="hybrid_azure_ad_join">Hybrid Azure AD Join</option>
                    <option value="azure_ad_join_intune">Azure AD + Intune</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Device Name Template</label>
                <input value={profileForm.apply_device_name_template} onChange={e => setProfileForm(p => ({ ...p, apply_device_name_template: e.target.value }))}
                  placeholder="e.g. CORP-%RAND:4%"
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Allowed Group (Azure AD Group)</label>
                <input value={profileForm.allowed_group} onChange={e => setProfileForm(p => ({ ...p, allowed_group: e.target.value }))}
                  placeholder="e.g. All-Windows-Devices"
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
              </div>
              <div className="grid grid-cols-3 gap-3">
                {[
                  { key: 'hide_privacy_settings', label: 'Hide Privacy' },
                  { key: 'hide_eula', label: 'Hide EULA' },
                  { key: 'auto_enroll_mdm', label: 'Auto MDM' },
                ].map(f => (
                  <label key={f.key} className="flex items-center gap-2 text-sm cursor-pointer">
                    <input type="checkbox" checked={(profileForm as any)[f.key]}
                      onChange={e => setProfileForm(p => ({ ...p, [f.key]: e.target.checked }))}
                      className="accent-blue-500" />
                    <span className="text-gray-300">{f.label}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="flex gap-2 mt-4 justify-end">
              <button onClick={() => { setShowAddProfile(false); setEditProfile(null); }} className="px-4 py-2 text-sm text-gray-400 hover:text-white">Cancel</button>
              <button onClick={saveProfile} disabled={saving || !profileForm.name}
                className="px-4 py-2 text-sm bg-blue-700 hover:bg-blue-600 rounded-lg disabled:opacity-50">
                {saving ? 'Saving…' : (editProfile ? 'Update' : 'Create')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
