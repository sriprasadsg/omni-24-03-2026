import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';

interface EmailThreat {
  id: string;
  threat_type: string;
  severity: string;
  sender: string;
  recipient: string;
  subject: string;
  verdict: string;
  confidence: number;
  detected_at: string;
  status: string;
}

interface Domain {
  id: string;
  domain: string;
  spf: string;
  dkim: string;
  dmarc_policy: string;
  dmarc_pct: number;
  health_score: number;
  last_checked: string;
}

interface Quarantine {
  id: string;
  sender: string;
  recipient: string;
  subject: string;
  reason: string;
  received_at: string;
  status: string;
}

interface Summary {
  threats_24h: number;
  quarantined_emails: number;
  monitored_domains: number;
  failing_dmarc: number;
}

const SEV_COLORS: Record<string, string> = {
  critical: 'bg-red-900/40 text-red-300 border-red-700',
  high: 'bg-orange-900/40 text-orange-300 border-orange-700',
  medium: 'bg-yellow-900/40 text-yellow-300 border-yellow-700',
  low: 'bg-gray-700 text-gray-300 border-gray-600',
};

const DMARC_COLOR = (policy: string) =>
  policy === 'reject' ? 'text-green-400' : policy === 'quarantine' ? 'text-yellow-400' : 'text-red-400';

type Tab = 'threats' | 'domains' | 'quarantine';

export default function EmailSecurityDashboard() {
  const [threats, setThreats] = useState<EmailThreat[]>([]);
  const [domains, setDomains] = useState<Domain[]>([]);
  const [quarantine, setQuarantine] = useState<Quarantine[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [tab, setTab] = useState<Tab>('threats');
  const [seeding, setSeeding] = useState(false);

  useEffect(() => { loadAll(); }, []);

  async function loadAll() {
    try {
      const [tRes, dRes, qRes, sRes] = await Promise.all([
        authFetch('/api/email-security/threats'),
        authFetch('/api/email-security/domains'),
        authFetch('/api/email-security/quarantine'),
        authFetch('/api/email-security/summary'),
      ]);
      const [t, d, q, s] = await Promise.all([tRes.json(), dRes.json(), qRes.json(), sRes.json()]);
      setThreats(t.threats || []);
      setDomains(d.domains || []);
      setQuarantine(q.items || []);
      setSummary(s);
    } catch (err) { console.error(err); }
  }

  async function seedData() {
    setSeeding(true);
    try {
      await authFetch('/api/email-security/seed', { method: 'POST' });
      loadAll();
    } finally { setSeeding(false); }
  }

  async function releaseEmail(id: string) {
    await authFetch(`/api/email-security/quarantine/${id}/release`, { method: 'POST' });
    loadAll();
  }

  const TABS: { key: Tab; label: string }[] = [
    { key: 'threats', label: `Threats (${threats.length})` },
    { key: 'domains', label: `Domain Health (${domains.length})` },
    { key: 'quarantine', label: `Quarantine (${quarantine.length})` },
  ];

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Email Security</h1>
          <p className="text-gray-400 text-sm mt-1">Phishing detection, DMARC/SPF/DKIM enforcement, quarantine management</p>
        </div>
        <button onClick={seedData} disabled={seeding}
          className="bg-gray-700 hover:bg-gray-600 disabled:opacity-50 px-4 py-2 rounded-lg text-sm">
          {seeding ? 'Loading…' : 'Load Demo Data'}
        </button>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {[
            { label: 'Threats (24h)', value: summary.threats_24h, color: summary.threats_24h > 0 ? 'text-red-400' : 'text-green-400' },
            { label: 'Quarantined', value: summary.quarantined_emails, color: summary.quarantined_emails > 0 ? 'text-yellow-400' : 'text-green-400' },
            { label: 'Domains Monitored', value: summary.monitored_domains, color: 'text-blue-400' },
            { label: 'Failing DMARC', value: summary.failing_dmarc, color: summary.failing_dmarc > 0 ? 'text-red-400' : 'text-green-400' },
          ].map(c => (
            <div key={c.label} className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
              <div className={`text-3xl font-bold ${c.color}`}>{c.value}</div>
              <div className="text-xs text-gray-400 mt-1">{c.label}</div>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2 mb-4 border-b border-gray-700 pb-2">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-3 py-1.5 rounded-t text-sm font-medium ${tab === t.key ? 'text-blue-300 border-b-2 border-blue-500 -mb-2 bg-blue-900/10' : 'text-gray-400 hover:text-white'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'threats' && (
        threats.length === 0 ? (
          <div className="text-center py-12 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
            <div className="text-4xl mb-3">📧</div><p>No email threats detected — load demo data</p>
          </div>
        ) : (
          <div className="space-y-2">
            {threats.map(t => (
              <div key={t.id} className={`bg-gray-800 rounded-xl p-4 border ${t.severity === 'critical' ? 'border-red-800' : 'border-gray-700'}`}>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-xs px-2 py-0.5 rounded border font-medium capitalize ${SEV_COLORS[t.severity] || ''}`}>
                        {t.severity}
                      </span>
                      <span className="text-xs text-gray-400 capitalize">{t.threat_type.replace(/_/g, ' ')}</span>
                      <span className={`text-xs capitalize ${t.verdict === 'malicious' ? 'text-red-400' : t.verdict === 'suspicious' ? 'text-yellow-400' : t.verdict === 'quarantined' ? 'text-orange-400' : 'text-green-400'}`}>
                        {t.verdict}
                      </span>
                    </div>
                    <p className="text-sm font-medium truncate">{t.subject}</p>
                    <div className="flex gap-4 text-xs text-gray-400 mt-1">
                      <span>From: <span className="text-white">{t.sender}</span></span>
                      <span>To: {t.recipient}</span>
                      <span>Conf: {Math.round(t.confidence * 100)}%</span>
                      <span>{new Date(t.detected_at).toLocaleString()}</span>
                    </div>
                  </div>
                  <span className={`text-xs capitalize ml-3 ${t.status === 'open' ? 'text-yellow-400' : 'text-green-400'}`}>{t.status}</span>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {tab === 'domains' && (
        domains.length === 0 ? (
          <div className="text-center py-12 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
            <p>No domains — load demo data</p>
          </div>
        ) : (
          <div className="space-y-3">
            {domains.map(d => (
              <div key={d.id} className="bg-gray-800 rounded-xl p-5 border border-gray-700">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-mono font-semibold">{d.domain}</h3>
                  <div className="flex items-center gap-2">
                    <div className="w-20 bg-gray-700 rounded-full h-2">
                      <div className={`h-2 rounded-full ${d.health_score >= 80 ? 'bg-green-500' : d.health_score >= 60 ? 'bg-yellow-500' : 'bg-red-500'}`}
                        style={{ width: `${d.health_score}%` }} />
                    </div>
                    <span className={`text-sm font-bold ${d.health_score >= 80 ? 'text-green-400' : d.health_score >= 60 ? 'text-yellow-400' : 'text-red-400'}`}>
                      {d.health_score}
                    </span>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-4 text-sm">
                  <div>
                    <span className="text-gray-400 text-xs">SPF</span>
                    <p className={`font-medium capitalize ${d.spf === 'pass' ? 'text-green-400' : 'text-red-400'}`}>{d.spf}</p>
                  </div>
                  <div>
                    <span className="text-gray-400 text-xs">DKIM</span>
                    <p className={`font-medium capitalize ${d.dkim === 'pass' ? 'text-green-400' : 'text-red-400'}`}>{d.dkim}</p>
                  </div>
                  <div>
                    <span className="text-gray-400 text-xs">DMARC Policy</span>
                    <p className={`font-medium capitalize font-mono ${DMARC_COLOR(d.dmarc_policy)}`}>
                      {d.dmarc_policy} ({d.dmarc_pct}%)
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {tab === 'quarantine' && (
        quarantine.length === 0 ? (
          <div className="text-center py-12 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
            <div className="text-4xl mb-3">✅</div><p>Quarantine is empty</p>
          </div>
        ) : (
          <div className="space-y-2">
            {quarantine.map(q => (
              <div key={q.id} className="bg-gray-800 rounded-xl p-4 border border-gray-700 flex items-center justify-between">
                <div className="flex-1">
                  <p className="font-medium text-sm truncate">{q.subject}</p>
                  <div className="flex gap-4 text-xs text-gray-400 mt-1">
                    <span>From: {q.sender}</span>
                    <span>To: {q.recipient}</span>
                    <span className="text-orange-300 capitalize">{q.reason.replace(/_/g, ' ')}</span>
                    <span>{new Date(q.received_at).toLocaleString()}</span>
                  </div>
                </div>
                {q.status === 'quarantined' && (
                  <button onClick={() => releaseEmail(q.id)}
                    className="ml-4 bg-green-900/40 hover:bg-green-900/70 border border-green-700 px-3 py-1.5 rounded text-xs text-green-300">
                    Release
                  </button>
                )}
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
}
