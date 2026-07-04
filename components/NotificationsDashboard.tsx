import React, { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

type Tab = 'notifications' | 'scanner';

export const NotificationsDashboard: React.FC = () => {
  const [tab, setTab] = useState<Tab>('notifications');
  const [loading, setLoading] = useState(false);
  // Channels
  const [channels, setChannels] = useState<any[]>([]);
  const [showChanForm, setShowChanForm] = useState(false);
  const [chanForm, setChanForm] = useState<any>({});
  // Rules
  const [rules, setRules] = useState<any[]>([]);
  const [showRuleForm, setShowRuleForm] = useState(false);
  const [ruleForm, setRuleForm] = useState<any>({});
  // Scanner
  const [domain, setDomain] = useState('');
  const [scanResult, setScanResult] = useState<any>(null);
  const [scanning, setScanning] = useState(false);
  const [scheduled, setScheduled] = useState<any[]>([]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      if (tab === 'notifications') {
        const [cr, rr] = await Promise.all([
          (await authFetch('/api/notifications/channels')).json(),
          (await authFetch('/api/notifications/rules')).json(),
        ]);
        setChannels(cr.items || []);
        setRules(rr.items || []);
      } else {
        const sr = await (await authFetch('/api/domain-scanner/scheduled')).json();
        setScheduled(sr.items || []);
      }
    } catch { showToast('Failed to load', 'error'); }
    finally { setLoading(false); }
  }, [tab]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const submitChannel = async () => {
    try {
      const res = await authFetch('/api/notifications/channels', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(chanForm) });
      if (!res.ok) throw new Error(await res.text());
      showToast('Channel created', 'success'); setShowChanForm(false); setChanForm({}); fetchData();
    } catch { showToast('Failed', 'error'); }
  };

  const submitRule = async () => {
    try {
      const res = await authFetch('/api/notifications/rules', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(ruleForm) });
      if (!res.ok) throw new Error(await res.text());
      showToast('Rule created', 'success'); setShowRuleForm(false); setRuleForm({}); fetchData();
    } catch { showToast('Failed', 'error'); }
  };

  const handleScan = async () => {
    if (!domain) return;
    setScanning(true); setScanResult(null);
    try {
      const res = await (await authFetch(`/api/domain-scanner/scan?domain=${encodeURIComponent(domain)}`)).json();
      setScanResult(res);
    } catch { showToast('Scan failed', 'error'); }
    finally { setScanning(false); }
  };

  const scheduleDomain = async () => {
    if (!domain) return;
    try {
      const res = await authFetch('/api/domain-scanner/scheduled', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({domain})});
      if (!res.ok) throw new Error(await res.text());
      showToast('Scheduled', 'success'); fetchData();
    } catch { showToast('Failed', 'error'); }
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-1 border-b dark:border-gray-700">
        <button onClick={() => setTab('notifications')} className={`px-4 py-2 text-sm font-medium rounded-t ${tab === 'notifications' ? 'bg-white dark:bg-gray-800 border border-b-0 text-blue-600' : 'text-gray-500'}`}>Notifications</button>
        <button onClick={() => setTab('scanner')} className={`px-4 py-2 text-sm font-medium rounded-t ${tab === 'scanner' ? 'bg-white dark:bg-gray-800 border border-b-0 text-blue-600' : 'text-gray-500'}`}>Domain Scanner</button>
      </div>

      {tab === 'notifications' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Channels */}
          <div className="space-y-2">
            <div className="flex items-center justify-between"><h3 className="text-sm font-semibold">Channels</h3>
              <button onClick={() => setShowChanForm(!showChanForm)} className="px-3 py-1 text-xs bg-blue-600 text-white rounded">+ Channel</button></div>
            {showChanForm && (
              <div className="grid grid-cols-2 gap-2 p-3 bg-gray-50 dark:bg-gray-800 rounded text-xs">
                <input placeholder="Name" className="p-1 border rounded dark:bg-gray-700" onChange={e => setChanForm({...chanForm, name: e.target.value})} />
                <select className="p-1 border rounded dark:bg-gray-700" onChange={e => setChanForm({...chanForm, type: e.target.value})}>
                  <option value="">Type</option><option value="slack">Slack</option><option value="email">Email</option><option value="webhook">Webhook</option>
                </select>
                <input placeholder="URL/Email" className="p-1 border rounded dark:bg-gray-700 col-span-2" onChange={e => setChanForm({
                  ...chanForm,
                  config: chanForm.type === 'webhook' ? { webhook_url: e.target.value }
                    : chanForm.type === 'email' ? { email: e.target.value }
                    : { url: e.target.value },
                })} />
                <button onClick={submitChannel} className="px-2 py-1 bg-blue-600 text-white rounded col-span-2">Create</button>
              </div>
            )}
            {channels.map((c, i) => <div key={i} className="p-2 bg-white dark:bg-gray-800 rounded shadow-sm text-xs"><span className="font-medium">{c.name}</span> — {c.type}</div>)}
            {!loading && channels.length === 0 && <p className="text-xs text-gray-400 italic">No channels.</p>}
          </div>

          {/* Rules */}
          <div className="space-y-2">
            <div className="flex items-center justify-between"><h3 className="text-sm font-semibold">Routing Rules</h3>
              <button onClick={() => setShowRuleForm(!showRuleForm)} className="px-3 py-1 text-xs bg-blue-600 text-white rounded">+ Rule</button></div>
            {showRuleForm && (
              <div className="grid grid-cols-2 gap-2 p-3 bg-gray-50 dark:bg-gray-800 rounded text-xs">
                <select className="p-1 border rounded dark:bg-gray-700" onChange={e => setRuleForm({...ruleForm, event_type: e.target.value})}>
                  <option value="">Event</option><option value="finding_created">Finding Created</option><option value="control_failed">Control Failed</option><option value="evidence_expired">Evidence Expired</option>
                </select>
                <input placeholder="Channel IDs (comma)" className="p-1 border rounded dark:bg-gray-700" onChange={e => setRuleForm({...ruleForm, channel_ids: e.target.value.split(',').map(s => s.trim()).filter(Boolean)})} />
                <button onClick={submitRule} className="px-2 py-1 bg-blue-600 text-white rounded col-span-2">Create</button>
              </div>
            )}
            {rules.map((r, i) => <div key={i} className="p-2 bg-white dark:bg-gray-800 rounded shadow-sm text-xs">{r.event_type} → {r.channel_ids?.join(', ')}</div>)}
            {!loading && rules.length === 0 && <p className="text-xs text-gray-400 italic">No rules.</p>}
          </div>
        </div>
      )}

      {tab === 'scanner' && (
        <div className="space-y-3">
          <div className="flex gap-2 items-end">
            <div className="flex-1">
              <label className="text-xs font-medium block mb-1">Domain to scan</label>
              <input value={domain} onChange={e => setDomain(e.target.value)} className="w-full p-2 border rounded text-sm dark:bg-gray-700 dark:border-gray-600" placeholder="example.com" />
            </div>
            <button onClick={handleScan} disabled={scanning} className="px-4 py-2 bg-blue-600 text-white text-sm rounded disabled:opacity-50">{scanning ? 'Scanning...' : 'Scan'}</button>
            <button onClick={scheduleDomain} className="px-4 py-2 bg-gray-600 text-white text-sm rounded">Schedule</button>
          </div>

          {scanResult && (
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 bg-white dark:bg-gray-800 rounded shadow-sm">
                <span className="font-medium">Subdomains</span>
                <ul className="mt-1 list-disc list-inside text-gray-600">{scanResult.subdomains?.map((s: string, i: number) => <li key={i}>{s}</li>)}</ul>
              </div>
              <div className="p-3 bg-white dark:bg-gray-800 rounded shadow-sm">
                <span className="font-medium">Open Ports</span>
                <div className="mt-1 text-gray-600">{Object.entries(scanResult.open_ports || {}).filter(([_,v]) => v).map(([p]) => p).join(', ') || 'None'}</div>
              </div>
              {scanResult.tls?.expiry && (
                <div className="p-3 bg-white dark:bg-gray-800 rounded shadow-sm">
                  <span className="font-medium">TLS</span>
                  <div className="text-gray-600">Expiry: {scanResult.tls.expiry}<br/>Issuer: {scanResult.tls.issuer}</div>
                </div>
              )}
              <div className="p-3 bg-white dark:bg-gray-800 rounded shadow-sm">
                <span className="font-medium">Scheduled</span>
                <ul className="mt-1 text-gray-600">{scheduled.map((s: any, i: number) => <li key={i}>{s.domain} ({s.status})</li>)}</ul>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
