import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';

interface Integration {
  id: string;
  provider: string;
  name: string;
  enabled: boolean;
  status: string;
  created_at: string;
  last_polled: string | null;
  last_poll_count: number;
  config: Record<string, string>;
}

interface Provider {
  name: string;
  icon: string;
  required_fields: string[];
  optional_fields: string[];
  description: string;
}

interface Summary {
  total: number;
  enabled: number;
  by_provider: Record<string, number>;
  supported_providers: string[];
}

const PROVIDER_ICONS: Record<string, string> = {
  azure_defender: '🔵',
  microsoft_sentinel: '🔵',
  gcp_scc: '🟢',
  gcp_chronicle: '🟢',
  aws_guardduty: '🟠',
  aws_securityhub: '🟠',
};

const PROVIDER_COLORS: Record<string, string> = {
  azure: 'border-blue-500 bg-blue-900/10',
  gcp: 'border-green-500 bg-green-900/10',
  aws: 'border-orange-500 bg-orange-900/10',
};

function providerColor(provider: string) {
  if (provider.startsWith('azure') || provider.startsWith('microsoft')) return PROVIDER_COLORS.azure;
  if (provider.startsWith('gcp')) return PROVIDER_COLORS.gcp;
  return PROVIDER_COLORS.aws;
}

export default function CloudIntegrationsDashboard() {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [providers, setProviders] = useState<Record<string, Provider>>({});
  const [summary, setSummary] = useState<Summary | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState('');
  const [form, setForm] = useState<Record<string, string>>({});
  const [formName, setFormName] = useState('');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Record<string, any>>({});

  useEffect(() => { loadAll(); }, []);

  async function loadAll() {
    try {
      const [iRes, pRes, sRes] = await Promise.all([
        authFetch('/api/cloud-integrations'),
        authFetch('/api/cloud-integrations/providers'),
        authFetch('/api/cloud-integrations/summary'),
      ]);
      const [i, p, s] = await Promise.all([iRes.json(), pRes.json(), sRes.json()]);
      setIntegrations(i.integrations || []);
      setProviders(p.providers || {});
      setSummary(s);
    } catch (e) { console.error(e); }
  }

  async function createIntegration() {
    if (!selectedProvider) return;
    setSaving(true);
    try {
      const r = await authFetch('/api/cloud-integrations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: selectedProvider, name: formName || providers[selectedProvider]?.name, config: form }),
      });
      if (r.ok) { loadAll(); setShowAdd(false); setForm({}); setFormName(''); setSelectedProvider(''); }
      else { const d = await r.json(); alert(d.detail || 'Failed to create'); }
    } finally { setSaving(false); }
  }

  async function toggleEnabled(id: string, enabled: boolean) {
    await authFetch(`/api/cloud-integrations/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !enabled }),
    });
    loadAll();
  }

  async function deleteIntegration(id: string) {
    if (!confirm('Delete this integration?')) return;
    await authFetch(`/api/cloud-integrations/${id}`, { method: 'DELETE' });
    loadAll();
  }

  async function testIntegration(id: string) {
    setTesting(id);
    try {
      const r = await authFetch(`/api/cloud-integrations/${id}/test`, { method: 'POST' });
      const d = await r.json();
      setTestResult(prev => ({ ...prev, [id]: d }));
    } finally { setTesting(null); }
  }

  const selectedProviderInfo = providers[selectedProvider];

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Cloud Integrations</h1>
          <p className="text-gray-400 text-sm mt-1">Connect Azure Defender, GCP SCC, AWS GuardDuty and more to ingest security events</p>
        </div>
        <button onClick={() => setShowAdd(true)} className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm font-medium">
          + Add Integration
        </button>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          {[
            { label: 'Total', value: summary.total, color: 'text-blue-400' },
            { label: 'Active', value: summary.enabled, color: 'text-green-400' },
            { label: 'Providers', value: Object.keys(summary.by_provider).length, color: 'text-purple-400' },
            { label: 'Supported', value: summary.supported_providers.length, color: 'text-gray-400' },
          ].map(c => (
            <div key={c.label} className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
              <div className={`text-3xl font-bold ${c.color}`}>{c.value}</div>
              <div className="text-xs text-gray-400 mt-1">{c.label}</div>
            </div>
          ))}
        </div>
      )}

      {integrations.length === 0 ? (
        <div className="text-center py-20 text-gray-500">
          <div className="text-5xl mb-4">☁️</div>
          <p className="text-lg">No cloud integrations connected yet</p>
          <p className="text-sm mt-2">Connect Azure, GCP, or AWS to start ingesting security events</p>
          <button onClick={() => setShowAdd(true)} className="mt-4 bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded-lg text-sm">
            Add First Integration
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {integrations.map(integ => (
            <div key={integ.id} className={`rounded-xl p-5 border ${providerColor(integ.provider)}`}>
              <div className="flex justify-between items-start mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-2xl">{PROVIDER_ICONS[integ.provider] || '🔗'}</span>
                  <div>
                    <h3 className="font-semibold">{integ.name}</h3>
                    <p className="text-xs text-gray-400">{integ.provider}</p>
                  </div>
                </div>
                <button
                  onClick={() => toggleEnabled(integ.id, integ.enabled)}
                  className={`relative inline-flex h-5 w-9 rounded-full transition-colors ${integ.enabled ? 'bg-green-500' : 'bg-gray-600'}`}
                >
                  <span className={`inline-block h-4 w-4 mt-0.5 rounded-full bg-white transition-transform ${integ.enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
                </button>
              </div>

              {integ.last_polled && (
                <div className="text-xs text-gray-400 mb-2">
                  Last polled: {new Date(integ.last_polled).toLocaleString()} · {integ.last_poll_count} events
                </div>
              )}

              {testResult[integ.id] && (
                <div className={`text-xs rounded px-2 py-1 mb-2 ${testResult[integ.id].success ? 'bg-green-900/30 text-green-300' : 'bg-red-900/30 text-red-300'}`}>
                  {testResult[integ.id].success
                    ? `✓ ${testResult[integ.id].events_ingested} events ingested`
                    : `✗ ${testResult[integ.id].error}`}
                </div>
              )}

              <div className="flex gap-2 mt-3">
                <button
                  onClick={() => testIntegration(integ.id)}
                  disabled={testing === integ.id}
                  className="flex-1 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 px-3 py-1.5 rounded text-xs"
                >
                  {testing === integ.id ? 'Testing...' : 'Test Poll'}
                </button>
                <button
                  onClick={() => deleteIntegration(integ.id)}
                  className="bg-red-900/40 hover:bg-red-900/70 px-3 py-1.5 rounded text-xs text-red-300"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showAdd && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-xl w-full max-w-lg border border-gray-600 max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex justify-between items-center mb-5">
                <h3 className="font-bold text-lg">Add Cloud Integration</h3>
                <button onClick={() => setShowAdd(false)} className="text-gray-400 hover:text-white">✕</button>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="text-sm text-gray-400 block mb-2">Provider *</label>
                  <div className="grid grid-cols-2 gap-2">
                    {Object.entries(providers).map(([id, p]) => (
                      <label key={id} className={`flex items-center gap-2 p-3 rounded-lg border cursor-pointer text-sm transition-colors ${
                        selectedProvider === id ? 'border-blue-500 bg-blue-900/20' : 'border-gray-600 hover:border-gray-400'
                      }`}>
                        <input type="radio" name="provider" value={id} checked={selectedProvider === id}
                          onChange={() => { setSelectedProvider(id); setForm({}); setFormName(''); }} className="sr-only" />
                        <span>{PROVIDER_ICONS[id] || '🔗'}</span>
                        <div>
                          <div className="font-medium text-xs leading-tight">{p.name}</div>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>

                {selectedProvider && selectedProviderInfo && (
                  <>
                    <div>
                      <label className="text-sm text-gray-400 block mb-1">Display Name</label>
                      <input value={formName} onChange={e => setFormName(e.target.value)}
                        placeholder={selectedProviderInfo.name}
                        className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white" />
                    </div>
                    <div className="text-sm text-gray-400 bg-gray-700/40 rounded-lg p-3">
                      {selectedProviderInfo.description}
                    </div>
                    <div className="space-y-2">
                      <p className="text-sm font-medium text-gray-300">Required Configuration</p>
                      {selectedProviderInfo.required_fields.map(field => (
                        <div key={field}>
                          <label className="text-xs text-gray-400 block mb-1 capitalize">{field.replace(/_/g, ' ')} *</label>
                          <input
                            type={field.includes('secret') || field.includes('password') || field.includes('key') ? 'password' : 'text'}
                            value={form[field] || ''}
                            onChange={e => setForm(prev => ({ ...prev, [field]: e.target.value }))}
                            className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm text-white"
                            placeholder={field.replace(/_/g, ' ')}
                          />
                        </div>
                      ))}
                      {selectedProviderInfo.optional_fields.length > 0 && (
                        <>
                          <p className="text-sm font-medium text-gray-400 pt-1">Optional</p>
                          {selectedProviderInfo.optional_fields.map(field => (
                            <div key={field}>
                              <label className="text-xs text-gray-400 block mb-1 capitalize">{field.replace(/_/g, ' ')}</label>
                              <input value={form[field] || ''} onChange={e => setForm(prev => ({ ...prev, [field]: e.target.value }))}
                                className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm text-white"
                                placeholder={field.replace(/_/g, ' ')} />
                            </div>
                          ))}
                        </>
                      )}
                    </div>
                  </>
                )}

                <div className="flex gap-3 pt-2">
                  <button onClick={createIntegration} disabled={saving || !selectedProvider}
                    className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-medium">
                    {saving ? 'Saving...' : 'Add Integration'}
                  </button>
                  <button onClick={() => setShowAdd(false)} className="px-4 py-2 rounded-lg border border-gray-600 text-sm">Cancel</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
