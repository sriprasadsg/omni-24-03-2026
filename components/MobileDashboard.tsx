import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

interface MdmDevice {
  id: string;
  udid: string;
  name: string;
  platform: string;
  os_version: string;
  model: string;
  manufacturer: string;
  serial_number: string;
  assigned_user: string;
  enrollment_status: string;
  compliance_status: string;
  last_seen: string;
  enrolled_at: string;
  policy_id: string | null;
}

interface MdmPolicy {
  id: string;
  name: string;
  platforms: string[];
  require_pin: boolean;
  require_encryption: boolean;
  block_rooted_jailbroken: boolean;
  min_os_version_ios: string;
  min_os_version_android: string;
  assigned_devices_count: number;
}

interface Summary { total: number; enrolled: number; non_compliant: number; ios: number; android: number; other: number; }

const STATUS_STYLES: Record<string, string> = {
  enrolled: 'bg-green-900/40 text-green-300',
  pending: 'bg-yellow-900/40 text-yellow-300',
  non_compliant: 'bg-red-900/40 text-red-300',
  wiped: 'bg-gray-700 text-gray-400',
  unenrolled: 'bg-gray-700 text-gray-400',
};

const PLATFORM_ICONS: Record<string, string> = { ios: '🍎', android: '🤖', windows: '🪟', macos: '🍏' };

const BLANK_DEVICE = { udid: '', name: '', platform: 'ios', os_version: '', model: '', manufacturer: '', serial_number: '', assigned_user: '', notes: '' };
const BLANK_POLICY = { name: '', description: '', platforms: ['ios', 'android'], require_pin: true, min_pin_length: 6, require_encryption: true, min_os_version_ios: '', min_os_version_android: '', block_rooted_jailbroken: true, max_inactivity_minutes: 15 };

export default function MobileDashboard() {
  const [tab, setTab] = useState<'devices' | 'policies' | 'enroll'>('devices');
  const [devices, setDevices] = useState<MdmDevice[]>([]);
  const [policies, setPolicies] = useState<MdmPolicy[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [platformFilter, setPlatformFilter] = useState('all');
  const [showAddDevice, setShowAddDevice] = useState(false);
  const [showAddPolicy, setShowAddPolicy] = useState(false);
  const [deviceForm, setDeviceForm] = useState({ ...BLANK_DEVICE });
  const [policyForm, setPolicyForm] = useState({ ...BLANK_POLICY });
  const [enrollUrl, setEnrollUrl] = useState<{ ios?: any; android?: any }>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => { loadAll(); }, []);

  async function loadAll() {
    try {
      const [dRes, pRes, sRes] = await Promise.all([
        authFetch('/api/mdm/devices'),
        authFetch('/api/mdm/policies'),
        authFetch('/api/mdm/summary'),
      ]);
      const [d, p, s] = await Promise.all([dRes.json(), pRes.json(), sRes.json()]);
      setDevices(d.devices || []);
      setPolicies(p.policies || []);
      setSummary(s);
    } catch (e) { console.error(e); }
  }

  async function enrollDevice() {
    setSaving(true);
    try {
      const r = await authFetch('/api/mdm/devices', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(deviceForm),
      });
      if (r.ok) {
        showToast('Device enrolled', 'success');
        setShowAddDevice(false);
        setDeviceForm({ ...BLANK_DEVICE });
        loadAll();
      } else {
        const d = await r.json();
        showToast(d.detail || 'Failed', 'error');
      }
    } finally { setSaving(false); }
  }

  async function remoteAction(id: string, action: string) {
    const confirmMsgs: Record<string, string> = {
      wipe: 'This will factory-reset the device. Proceed?',
      lock: 'Lock this device remotely?',
      reset_passcode: 'Reset the passcode on this device?',
      retire: 'Retire this device?',
    };
    if (confirmMsgs[action] && !confirm(confirmMsgs[action])) return;
    const r = await authFetch(`/api/mdm/devices/${id}/action`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action }),
    });
    if (r.ok) showToast(`Action '${action}' queued`, 'success');
    else { const d = await r.json(); showToast(d.detail || 'Failed', 'error'); }
  }

  async function savePolicy() {
    setSaving(true);
    try {
      const r = await authFetch('/api/mdm/policies', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(policyForm),
      });
      if (r.ok) {
        showToast('Policy created', 'success');
        setShowAddPolicy(false);
        setPolicyForm({ ...BLANK_POLICY });
        loadAll();
      } else { const d = await r.json(); showToast(d.detail || 'Failed', 'error'); }
    } finally { setSaving(false); }
  }

  async function getEnrollUrl(platform: string) {
    const r = await authFetch(`/api/mdm/enrollment-url/${platform}`);
    const d = await r.json();
    setEnrollUrl(prev => ({ ...prev, [platform]: d }));
  }

  const filtered = platformFilter === 'all' ? devices : devices.filter(d => d.platform === platformFilter);

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="flex justify-between items-start mb-6">
        <div>
          <h1 className="text-2xl font-bold">Mobile Device Management</h1>
          <p className="text-gray-400 text-sm mt-1">Manage iOS and Android devices, compliance policies, and remote actions</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowAddPolicy(true)} className="px-3 py-2 text-sm bg-blue-700 hover:bg-blue-600 rounded-lg">+ New Policy</button>
          <button onClick={() => setShowAddDevice(true)} className="px-3 py-2 text-sm bg-indigo-700 hover:bg-indigo-600 rounded-lg">+ Enroll Device</button>
        </div>
      </div>

      {/* Summary */}
      {summary && (
        <div className="grid grid-cols-3 md:grid-cols-6 gap-3 mb-6">
          {[
            { label: 'Total', value: summary.total, color: 'text-white' },
            { label: 'Enrolled', value: summary.enrolled, color: 'text-green-400' },
            { label: 'Non-Compliant', value: summary.non_compliant, color: 'text-red-400' },
            { label: 'iOS', value: summary.ios, color: 'text-blue-400' },
            { label: 'Android', value: summary.android, color: 'text-green-300' },
            { label: 'Other', value: summary.other, color: 'text-gray-400' },
          ].map(c => (
            <div key={c.label} className="bg-gray-800 rounded-lg p-3 text-center">
              <div className={`text-xl font-bold ${c.color}`}>{c.value}</div>
              <div className="text-xs text-gray-400 mt-0.5">{c.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-4 border-b border-gray-700">
        {(['devices', 'policies', 'enroll'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize ${tab === t ? 'border-b-2 border-blue-500 text-blue-400' : 'text-gray-400 hover:text-white'}`}>
            {t === 'enroll' ? 'Enrollment URLs' : t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {/* Devices */}
      {tab === 'devices' && (
        <>
          <div className="flex gap-2 mb-3">
            {['all', 'ios', 'android', 'windows', 'macos'].map(p => (
              <button key={p} onClick={() => setPlatformFilter(p)}
                className={`px-3 py-1 text-xs rounded-full capitalize ${platformFilter === p ? 'bg-blue-700 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
                {PLATFORM_ICONS[p] || ''} {p}
              </button>
            ))}
          </div>
          <div className="bg-gray-800 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-700/50 text-gray-400 text-xs uppercase">
                <tr>
                  <th className="px-4 py-3 text-left">Device</th>
                  <th className="px-4 py-3 text-left">Platform</th>
                  <th className="px-4 py-3 text-left">User</th>
                  <th className="px-4 py-3 text-left">Status</th>
                  <th className="px-4 py-3 text-left">Compliance</th>
                  <th className="px-4 py-3 text-left">Last Seen</th>
                  <th className="px-4 py-3 text-left">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {filtered.length === 0 && <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500">No devices</td></tr>}
                {filtered.map(d => (
                  <tr key={d.id} className="hover:bg-gray-700/30">
                    <td className="px-4 py-3">
                      <div className="text-white">{d.name || d.model || 'Unknown'}</div>
                      <div className="text-xs text-gray-500 font-mono">{d.udid.slice(0, 16)}…</div>
                    </td>
                    <td className="px-4 py-3 text-sm">{PLATFORM_ICONS[d.platform]} {d.platform} {d.os_version}</td>
                    <td className="px-4 py-3 text-sm text-gray-300">{d.assigned_user || '—'}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs capitalize ${STATUS_STYLES[d.enrollment_status] || 'bg-gray-700 text-gray-300'}`}>
                        {d.enrollment_status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs capitalize ${d.compliance_status === 'compliant' ? 'bg-green-900/40 text-green-300' : d.compliance_status === 'non_compliant' ? 'bg-red-900/40 text-red-300' : 'bg-gray-700 text-gray-400'}`}>
                        {d.compliance_status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-400">{d.last_seen ? new Date(d.last_seen).toLocaleString() : '—'}</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2 text-xs">
                        <button onClick={() => remoteAction(d.id, 'lock')} className="text-yellow-400 hover:text-yellow-300">Lock</button>
                        <button onClick={() => remoteAction(d.id, 'sync')} className="text-blue-400 hover:text-blue-300">Sync</button>
                        <button onClick={() => remoteAction(d.id, 'wipe')} className="text-red-400 hover:text-red-300">Wipe</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Policies */}
      {tab === 'policies' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {policies.length === 0 && <div className="col-span-3 text-center text-gray-500 py-12">No MDM policies yet</div>}
          {policies.map(p => (
            <div key={p.id} className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <div className="flex justify-between">
                <h3 className="font-medium text-white">{p.name}</h3>
                <button onClick={async () => { if (!confirm('Delete policy?')) return; await authFetch(`/api/mdm/policies/${p.id}`, { method: 'DELETE' }); loadAll(); }} className="text-xs text-red-400 hover:text-red-300">Delete</button>
              </div>
              <div className="mt-2 text-xs text-gray-400 space-y-1">
                <div>Platforms: {p.platforms.join(', ')}</div>
                <div className="flex gap-3">
                  <span className={p.require_pin ? 'text-green-400' : 'text-gray-500'}>PIN required</span>
                  <span className={p.require_encryption ? 'text-green-400' : 'text-gray-500'}>Encryption</span>
                  <span className={p.block_rooted_jailbroken ? 'text-green-400' : 'text-gray-500'}>No jailbreak</span>
                </div>
                {p.min_os_version_ios && <div>iOS min: {p.min_os_version_ios}</div>}
                {p.min_os_version_android && <div>Android min: {p.min_os_version_android}</div>}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Enrollment URLs */}
      {tab === 'enroll' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {['ios', 'android'].map(p => (
            <div key={p} className="bg-gray-800 rounded-lg p-6 border border-gray-700">
              <h3 className="font-medium text-lg mb-2">{PLATFORM_ICONS[p]} {p === 'ios' ? 'iOS' : 'Android'} Enrollment</h3>
              <p className="text-gray-400 text-sm mb-4">Generate a one-time enrollment link to send to a user or display as QR code.</p>
              <button onClick={() => getEnrollUrl(p)} className="px-4 py-2 text-sm bg-blue-700 hover:bg-blue-600 rounded-lg mb-4">Generate Enrollment URL</button>
              {enrollUrl[p as 'ios' | 'android'] && (
                <div className="bg-gray-900 rounded-lg p-3 mt-2">
                  <div className="text-xs text-gray-400 mb-1">Enrollment URL (valid 24 hours)</div>
                  <code className="text-xs text-green-400 break-all">{enrollUrl[p as 'ios' | 'android'].enrollment_url}</code>
                  <div className="text-xs text-gray-500 mt-2">Token: <span className="font-mono">{enrollUrl[p as 'ios' | 'android'].token}</span></div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Enroll Device Modal */}
      {showAddDevice && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-xl p-6 w-full max-w-md border border-gray-700">
            <h2 className="text-lg font-semibold mb-4">Enroll Mobile Device</h2>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-400 block mb-1">Platform</label>
                <select value={deviceForm.platform} onChange={e => setDeviceForm(p => ({ ...p, platform: e.target.value }))}
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm">
                  {['ios', 'android', 'windows', 'macos'].map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              {[
                { key: 'udid', label: 'UDID / Device ID *', placeholder: 'Unique device identifier' },
                { key: 'name', label: 'Device Name', placeholder: 'e.g. John\'s iPhone' },
                { key: 'model', label: 'Model', placeholder: 'e.g. iPhone 15 Pro' },
                { key: 'os_version', label: 'OS Version', placeholder: 'e.g. 17.5' },
                { key: 'assigned_user', label: 'Assigned User (UPN)', placeholder: 'user@company.com' },
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
              <button onClick={enrollDevice} disabled={saving || !deviceForm.udid}
                className="px-4 py-2 text-sm bg-indigo-700 hover:bg-indigo-600 rounded-lg disabled:opacity-50">
                {saving ? 'Enrolling…' : 'Enroll'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create Policy Modal */}
      {showAddPolicy && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-xl p-6 w-full max-w-md border border-gray-700 max-h-[90vh] overflow-y-auto">
            <h2 className="text-lg font-semibold mb-4">New MDM Policy</h2>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-400 block mb-1">Policy Name *</label>
                <input value={policyForm.name} onChange={e => setPolicyForm(p => ({ ...p, name: e.target.value }))}
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-400 block mb-1">iOS Min Version</label>
                  <input value={policyForm.min_os_version_ios} onChange={e => setPolicyForm(p => ({ ...p, min_os_version_ios: e.target.value }))}
                    placeholder="e.g. 16.0" className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Android Min Version</label>
                  <input value={policyForm.min_os_version_android} onChange={e => setPolicyForm(p => ({ ...p, min_os_version_android: e.target.value }))}
                    placeholder="e.g. 12" className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm" />
                </div>
              </div>
              <div className="space-y-2">
                {[
                  { key: 'require_pin', label: 'Require PIN/Passcode' },
                  { key: 'require_encryption', label: 'Require Device Encryption' },
                  { key: 'block_rooted_jailbroken', label: 'Block Rooted/Jailbroken Devices' },
                ].map(f => (
                  <label key={f.key} className="flex items-center gap-2 text-sm cursor-pointer">
                    <input type="checkbox" checked={(policyForm as any)[f.key]} onChange={e => setPolicyForm(p => ({ ...p, [f.key]: e.target.checked }))} className="accent-blue-500" />
                    <span className="text-gray-300">{f.label}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="flex gap-2 mt-4 justify-end">
              <button onClick={() => setShowAddPolicy(false)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">Cancel</button>
              <button onClick={savePolicy} disabled={saving || !policyForm.name}
                className="px-4 py-2 text-sm bg-blue-700 hover:bg-blue-600 rounded-lg disabled:opacity-50">
                {saving ? 'Saving…' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
