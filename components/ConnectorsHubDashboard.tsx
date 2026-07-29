import React, { useState, useEffect, useCallback } from 'react';

const API = '/api/connectors-hub';

type ConnectorStatus = 'connected' | 'disconnected' | 'error';

interface Connector {
  id: string;
  name: string;
  category: string;
  description: string;
  status: ConnectorStatus;
  auth_type: 'api_key' | 'oauth' | 'webhook' | 'certificate';
  last_sync?: string;
}

const CATEGORIES = [
  'Microsoft 365', 'Endpoint Security', 'Network', 'Cloud Providers',
  'Vulnerability', 'ITSM', 'Threat Intelligence', 'Syslog',
];

const MOCK_CONNECTORS: Connector[] = [
  { id: 'ms-defender', name: 'Microsoft Defender', category: 'Endpoint Security', description: 'Microsoft Defender for Endpoint telemetry', status: 'disconnected', auth_type: 'oauth' },
  { id: 'ms-entra', name: 'Microsoft Entra ID', category: 'Microsoft 365', description: 'Azure AD identity & sign-in logs', status: 'disconnected', auth_type: 'oauth' },
  { id: 'ms-intune', name: 'Microsoft Intune', category: 'Microsoft 365', description: 'Device compliance and MDM data', status: 'disconnected', auth_type: 'oauth' },
  { id: 'ms-o365', name: 'Microsoft 365', category: 'Microsoft 365', description: 'Email, Teams and SharePoint audit logs', status: 'disconnected', auth_type: 'oauth' },
  { id: 'crowdstrike', name: 'CrowdStrike Falcon', category: 'Endpoint Security', description: 'EDR detections and threat intelligence', status: 'disconnected', auth_type: 'api_key' },
  { id: 'sentinelone', name: 'SentinelOne', category: 'Endpoint Security', description: 'Threat detections and alerts', status: 'disconnected', auth_type: 'api_key' },
  { id: 'paloalto', name: 'Palo Alto Networks', category: 'Network', description: 'Firewall logs and threat prevention', status: 'disconnected', auth_type: 'syslog' as any },
  { id: 'fortinet', name: 'Fortinet FortiGate', category: 'Network', description: 'Next-gen firewall events', status: 'disconnected', auth_type: 'syslog' as any },
  { id: 'aws', name: 'AWS Security Hub', category: 'Cloud Providers', description: 'AWS GuardDuty, CloudTrail and SecurityHub', status: 'disconnected', auth_type: 'api_key' },
  { id: 'azure', name: 'Azure Security Center', category: 'Cloud Providers', description: 'Azure Defender and Sentinel integration', status: 'disconnected', auth_type: 'oauth' },
  { id: 'gcp', name: 'GCP Security Command', category: 'Cloud Providers', description: 'Google Cloud security findings', status: 'disconnected', auth_type: 'certificate' },
  { id: 'tenable', name: 'Tenable.io', category: 'Vulnerability', description: 'Vulnerability scan results and assets', status: 'disconnected', auth_type: 'api_key' },
  { id: 'qualys', name: 'Qualys VMDR', category: 'Vulnerability', description: 'Vulnerability management and detection', status: 'disconnected', auth_type: 'api_key' },
  { id: 'servicenow', name: 'ServiceNow', category: 'ITSM', description: 'Incident and change management sync', status: 'disconnected', auth_type: 'oauth' },
  { id: 'jira', name: 'Jira', category: 'ITSM', description: 'Issue tracking and project sync', status: 'disconnected', auth_type: 'api_key' },
  { id: 'thehive', name: 'TheHive', category: 'ITSM', description: 'Open-source SOAR & incident response platform', status: 'disconnected', auth_type: 'api_key' },
  { id: 'pagerduty', name: 'PagerDuty', category: 'ITSM', description: 'On-call incident alerting for security events', status: 'disconnected', auth_type: 'api_key' },
  { id: 'misp', name: 'MISP', category: 'Threat Intelligence', description: 'Open-source threat sharing platform', status: 'disconnected', auth_type: 'api_key' },
  { id: 'virustotal', name: 'VirusTotal', category: 'Threat Intelligence', description: 'File, URL and IP reputation lookups', status: 'disconnected', auth_type: 'api_key' },
  { id: 'syslog-linux', name: 'Linux Syslog', category: 'Syslog', description: 'RFC 5424 syslog from Linux hosts', status: 'disconnected', auth_type: 'webhook' },
];

const STATUS_COLOR: Record<ConnectorStatus, string> = {
  connected: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  disconnected: 'bg-slate-700/50 text-slate-400 border-slate-600/30',
  error: 'bg-red-500/20 text-red-400 border-red-500/30',
};

export default function ConnectorsHubDashboard() {
  const [connectors, setConnectors] = useState<Connector[]>(MOCK_CONNECTORS);
  const [tab, setTab] = useState<'all' | 'connected' | 'available'>('all');
  const [selected, setSelected] = useState<Connector | null>(null);
  const [configValue, setConfigValue] = useState('');
  const [saving, setSaving] = useState(false);
  const [filterCat, setFilterCat] = useState('');

  const load = useCallback(async () => {
    try {
      const r = await fetch(API, { headers: { Authorization: `Bearer ${sessionStorage.getItem('token')}` } });
      if (r.ok) {
        const data = await r.json();
        if (Array.isArray(data) && data.length > 0) setConnectors(data);
      }
    } catch { /* use mock */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const visible = connectors.filter(c => {
    if (tab === 'connected') return c.status === 'connected';
    if (tab === 'available') return c.status !== 'connected';
    return true;
  }).filter(c => !filterCat || c.category === filterCat);

  const grouped = CATEGORIES.reduce<Record<string, Connector[]>>((acc, cat) => {
    const items = visible.filter(c => c.category === cat);
    if (items.length) acc[cat] = items;
    return acc;
  }, {});

  const save = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      await fetch(`${API}/${selected.id}/configure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${sessionStorage.getItem('token')}` },
        body: JSON.stringify({ credential: configValue }),
      });
      setConnectors(prev => prev.map(c => c.id === selected.id ? { ...c, status: 'connected' } : c));
      setSelected(null);
      setConfigValue('');
    } catch { /* ignore */ }
    setSaving(false);
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Connectors Hub</h2>
        <span className="text-sm text-slate-400">{connectors.filter(c => c.status === 'connected').length} of {connectors.length} connected</span>
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex rounded-lg overflow-hidden border border-slate-700">
          {(['all', 'connected', 'available'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium capitalize transition-colors ${tab === t ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>
              {t}
            </button>
          ))}
        </div>
        <select value={filterCat} onChange={e => setFilterCat(e.target.value)}
          className="bg-slate-800 border border-slate-700 text-slate-300 text-sm rounded-lg px-3 py-2">
          <option value="">All Categories</option>
          {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      {Object.entries(grouped).map(([cat, items]) => (
        <div key={cat}>
          <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">{cat}</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {items.map(c => (
              <div key={c.id} className="bg-slate-800 border border-slate-700 rounded-xl p-4 flex flex-col gap-3">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="font-semibold text-white">{c.name}</div>
                    <div className="text-xs text-slate-400 mt-0.5">{c.description}</div>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full border font-medium capitalize ${STATUS_COLOR[c.status]}`}>
                    {c.status}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs text-slate-500">
                  <span>Auth: {c.auth_type.replace('_', ' ')}</span>
                  {c.last_sync && <span>Synced {c.last_sync}</span>}
                </div>
                <button onClick={() => { setSelected(c); setConfigValue(''); }}
                  className="w-full py-1.5 rounded-lg text-sm font-medium bg-blue-600/20 text-blue-400 border border-blue-600/30 hover:bg-blue-600/30 transition-colors">
                  Configure
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}

      {selected && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-white">Configure {selected.name}</h3>
              <button onClick={() => setSelected(null)} className="text-slate-400 hover:text-white text-xl">&times;</button>
            </div>
            <div className="space-y-2">
              <label className="text-sm text-slate-300">
                {selected.auth_type === 'api_key' ? 'API Key' : selected.auth_type === 'oauth' ? 'Client Secret / Token' : 'Webhook URL or Certificate'}
              </label>
              <input type="password" value={configValue} onChange={e => setConfigValue(e.target.value)}
                placeholder="Enter credential..."
                className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setSelected(null)} className="flex-1 py-2 rounded-lg border border-slate-600 text-slate-300 text-sm hover:bg-slate-800 transition-colors">Cancel</button>
              <button onClick={save} disabled={saving || !configValue}
                className="flex-1 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50">
                {saving ? 'Saving...' : 'Save & Connect'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
