import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';

interface DSR {
  id: string;
  reference_number: string;
  request_type: string;
  data_subject_name: string;
  data_subject_email: string;
  regulation: string;
  status: string;
  created_at: string;
  due_date: string;
  completed_at: string | null;
  is_overdue: boolean;
  sla_days: number;
}

interface Breach {
  id: string;
  reference: string;
  description: string;
  risk_level: string;
  estimated_subjects_affected: number;
  status: string;
  reported_at: string;
  authority_notification_deadline: string | null;
  authority_notified: boolean;
}

// Matches the actual /api/privacy/summary response shape
interface Summary {
  total_dsrs: number;
  open_dsrs: number;
  overdue_dsrs: number;
  open_breaches: number;
  consent_granted: number;
  processing_activities?: number;
}

const DSR_TYPES = ['access', 'erasure', 'portability', 'rectification', 'restriction', 'objection', 'opt_out_sale', 'know'];
const REGULATIONS = ['GDPR', 'CCPA', 'PIPEDA', 'LGPD', 'OTHER'];

type Tab = 'dsr' | 'breaches' | 'activities';

export default function PrivacyDashboard() {
  const [tab, setTab] = useState<Tab>('dsr');
  const [dsrs, setDsrs] = useState<DSR[]>([]);
  const [breaches, setBreaches] = useState<Breach[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [activities, setActivities] = useState<any[]>([]);
  const [showCreateDSR, setShowCreateDSR] = useState(false);
  const [showCreateBreach, setShowCreateBreach] = useState(false);
  const [dsrForm, setDsrForm] = useState({
    request_type: 'access',
    data_subject_name: '',
    data_subject_email: '',
    regulation: 'GDPR',
    description: '',
  });
  const [breachForm, setBreachForm] = useState({
    description: '',
    risk_level: 'high',
    breach_type: 'unauthorized_access',
    estimated_subjects_affected: 0,
    notification_required: true,
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => { loadAll(); }, []);

  async function loadAll() {
    try {
      const [dRes, bRes, sRes, aRes] = await Promise.all([
        authFetch('/api/privacy/dsr'),
        authFetch('/api/privacy/breaches'),
        authFetch('/api/privacy/summary'),
        authFetch('/api/privacy/processing-activities'),
      ]);
      const [d, b, s, a] = await Promise.all([dRes.json(), bRes.json(), sRes.json(), aRes.json()]);
      setDsrs(d.dsrs || []);
      setBreaches(b.breaches || []);
      setSummary(s);
      setActivities(a.activities || []);
    } catch (e) { console.error(e); }
  }

  async function createDSR() {
    setSaving(true);
    try {
      const r = await authFetch('/api/privacy/dsr', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dsrForm),
      });
      if (r.ok) {
        loadAll();
        setShowCreateDSR(false);
        setDsrForm({ request_type: 'access', data_subject_name: '', data_subject_email: '', regulation: 'GDPR', description: '' });
      } else {
        const d = await r.json();
        alert(d.detail || 'Failed to create DSR');
      }
    } finally { setSaving(false); }
  }

  async function createBreach() {
    setSaving(true);
    try {
      const r = await authFetch('/api/privacy/breaches', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(breachForm),
      });
      if (r.ok) {
        loadAll();
        setShowCreateBreach(false);
        setBreachForm({ description: '', risk_level: 'high', breach_type: 'unauthorized_access', estimated_subjects_affected: 0, notification_required: true });
      } else {
        const d = await r.json();
        alert(d.detail || 'Failed to report breach');
      }
    } finally { setSaving(false); }
  }

  async function updateDSRStatus(id: string, status: string) {
    await authFetch(`/api/privacy/dsr/${id}/status`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    loadAll();
  }

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Privacy & Data Protection</h1>
          <p className="text-gray-400 text-sm mt-1">GDPR/CCPA compliance — DSRs, breach notifications, consent management</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowCreateDSR(true)} className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm font-medium">
            + New DSR
          </button>
          <button onClick={() => setShowCreateBreach(true)} className="bg-red-700 hover:bg-red-600 px-4 py-2 rounded-lg text-sm font-medium">
            + Report Breach
          </button>
        </div>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
            <div className="text-3xl font-bold text-blue-400">{summary.open_dsrs}</div>
            <div className="text-xs text-gray-400 mt-1">Open DSRs</div>
          </div>
          <div className="bg-gray-800 rounded-xl p-4 border border-red-900/50 text-center">
            <div className={`text-3xl font-bold ${summary.overdue_dsrs > 0 ? 'text-red-400' : 'text-green-400'}`}>{summary.overdue_dsrs}</div>
            <div className="text-xs text-gray-400 mt-1">Overdue DSRs</div>
          </div>
          <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
            <div className={`text-3xl font-bold ${summary.open_breaches > 0 ? 'text-orange-400' : 'text-green-400'}`}>{summary.open_breaches}</div>
            <div className="text-xs text-gray-400 mt-1">Open Breaches</div>
          </div>
          <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 text-center">
            <div className="text-3xl font-bold text-purple-400">{summary.consent_granted}</div>
            <div className="text-xs text-gray-400 mt-1">Consent Records</div>
          </div>
        </div>
      )}

      <div className="flex gap-2 mb-4 border-b border-gray-700 pb-2">
        {([['dsr', 'Data Subject Requests'], ['breaches', 'Breach Register'], ['activities', 'Processing Activities']] as [Tab, string][]).map(([t, label]) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium rounded-t transition-colors ${tab === t ? 'text-blue-300 bg-blue-900/20 border-b-2 border-blue-500' : 'text-gray-400 hover:text-white'}`}>
            {label}
            {t === 'dsr' && dsrs.length > 0 && (
              <span className="ml-1.5 text-xs bg-blue-900/50 text-blue-300 px-1.5 py-0.5 rounded-full">{dsrs.length}</span>
            )}
            {t === 'breaches' && breaches.length > 0 && (
              <span className="ml-1.5 text-xs bg-red-900/50 text-red-300 px-1.5 py-0.5 rounded-full">{breaches.length}</span>
            )}
          </button>
        ))}
      </div>

      {tab === 'dsr' && (
        <div className="space-y-3">
          {dsrs.length === 0 ? (
            <div className="text-center py-12 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
              <div className="text-4xl mb-3">📋</div>
              <p>No data subject requests</p>
              <p className="text-sm mt-1">Click "+ New DSR" to log a request</p>
            </div>
          ) : (
            dsrs.map(dsr => (
              <div key={dsr.id} className={`bg-gray-800 rounded-xl p-4 border ${dsr.is_overdue ? 'border-red-700' : 'border-gray-700'}`}>
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="text-xs bg-blue-900/40 text-blue-300 border border-blue-700 px-2 py-0.5 rounded font-medium capitalize">
                        {dsr.request_type.replace(/_/g, ' ')}
                      </span>
                      <span className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded">{dsr.regulation}</span>
                      {dsr.is_overdue && <span className="text-xs bg-red-900/50 text-red-300 border border-red-700 px-2 py-0.5 rounded font-bold">OVERDUE</span>}
                      {dsr.reference_number && <span className="text-xs text-gray-500">{dsr.reference_number}</span>}
                    </div>
                    <p className="font-medium">{dsr.data_subject_name}</p>
                    <p className="text-gray-400 text-sm">{dsr.data_subject_email}</p>
                    <div className="flex gap-4 text-xs text-gray-500 mt-1 flex-wrap">
                      <span>Received: {new Date(dsr.created_at).toLocaleDateString()}</span>
                      <span className={dsr.is_overdue ? 'text-red-400 font-medium' : ''}>
                        Due: {new Date(dsr.due_date).toLocaleDateString()}
                      </span>
                      <span>SLA: {dsr.sla_days} days</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 ml-4">
                    <span className={`text-xs font-medium capitalize ${dsr.status === 'completed' ? 'text-green-400' : dsr.status === 'overdue' ? 'text-red-400' : 'text-yellow-400'}`}>
                      {dsr.status.replace(/_/g, ' ')}
                    </span>
                    {dsr.status !== 'completed' && dsr.status !== 'denied' && dsr.status !== 'withdrawn' && (
                      <button onClick={() => updateDSRStatus(dsr.id, 'completed')}
                        className="bg-green-900/40 hover:bg-green-900/70 border border-green-700 px-2 py-1 rounded text-xs text-green-300">
                        Complete
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {tab === 'breaches' && (
        <div className="space-y-3">
          {breaches.length === 0 ? (
            <div className="text-center py-12 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
              <div className="text-4xl mb-3">✅</div>
              <p>No breaches recorded</p>
              <p className="text-sm mt-1">Use "+ Report Breach" to log a data breach incident</p>
            </div>
          ) : (
            breaches.map(b => (
              <div key={b.id} className={`bg-gray-800 rounded-xl p-4 border ${b.status === 'open' ? 'border-orange-800' : 'border-gray-700'}`}>
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className={`text-xs px-2 py-0.5 rounded font-medium border capitalize ${
                        b.risk_level === 'critical' ? 'bg-red-900/40 text-red-300 border-red-700' :
                        b.risk_level === 'high'     ? 'bg-orange-900/40 text-orange-300 border-orange-700' :
                                                      'bg-yellow-900/40 text-yellow-300 border-yellow-700'
                      }`}>{b.risk_level} risk</span>
                      <span className={`text-xs font-medium capitalize ${b.status === 'closed' ? 'text-gray-400' : 'text-orange-400'}`}>
                        {b.status}
                      </span>
                      {b.reference && <span className="text-xs text-gray-500">{b.reference}</span>}
                      {!b.authority_notified && b.status === 'open' && (
                        <span className="text-xs bg-red-900/40 text-red-300 border border-red-700 px-2 py-0.5 rounded">Authority Not Notified</span>
                      )}
                    </div>
                    <p className="text-sm text-gray-200">{b.description}</p>
                    <div className="flex gap-4 text-xs text-gray-400 mt-1 flex-wrap">
                      <span>{(b.estimated_subjects_affected || 0).toLocaleString()} subjects affected</span>
                      <span>Reported: {new Date(b.reported_at).toLocaleDateString()}</span>
                      {b.authority_notification_deadline && (
                        <span className={!b.authority_notified ? 'text-red-400 font-medium' : 'text-gray-400'}>
                          72h deadline: {new Date(b.authority_notification_deadline).toLocaleString()}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {tab === 'activities' && (
        <div className="space-y-3">
          {activities.length === 0 ? (
            <div className="text-center py-12 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
              <div className="text-4xl mb-3">📋</div>
              <p>Record of Processing Activities (ROPA)</p>
              <p className="text-sm mt-2">Document your data processing activities to maintain GDPR Article 30 compliance</p>
            </div>
          ) : (
            activities.map((a, i) => (
              <div key={a.id || i} className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="font-medium">{a.name}</h3>
                    <p className="text-gray-400 text-sm mt-0.5">{a.purpose}</p>
                    <div className="flex gap-3 mt-1 text-xs text-gray-500">
                      {a.legal_basis && <span>Legal basis: {a.legal_basis}</span>}
                      {a.dpia_required && <span className={a.dpia_completed ? 'text-green-400' : 'text-yellow-400'}>DPIA {a.dpia_completed ? 'complete' : 'required'}</span>}
                    </div>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Create DSR Modal */}
      {showCreateDSR && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-xl w-full max-w-md border border-gray-600">
            <div className="p-6">
              <div className="flex justify-between items-center mb-5">
                <h3 className="font-bold text-lg">New Data Subject Request</h3>
                <button onClick={() => setShowCreateDSR(false)} className="text-gray-400 hover:text-white text-xl">✕</button>
              </div>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Request Type *</label>
                  <select value={dsrForm.request_type} onChange={e => setDsrForm(p => ({ ...p, request_type: e.target.value }))}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white">
                    {DSR_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Data Subject Name *</label>
                  <input value={dsrForm.data_subject_name} onChange={e => setDsrForm(p => ({ ...p, data_subject_name: e.target.value }))}
                    placeholder="Full name" className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white" />
                </div>
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Email *</label>
                  <input type="email" value={dsrForm.data_subject_email} onChange={e => setDsrForm(p => ({ ...p, data_subject_email: e.target.value }))}
                    placeholder="subject@example.com" className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white" />
                </div>
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Regulation</label>
                  <select value={dsrForm.regulation} onChange={e => setDsrForm(p => ({ ...p, regulation: e.target.value }))}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white">
                    {REGULATIONS.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Description</label>
                  <textarea value={dsrForm.description} onChange={e => setDsrForm(p => ({ ...p, description: e.target.value }))}
                    rows={2} placeholder="Optional details about the request"
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white resize-none" />
                </div>
                <div className="flex gap-3 pt-2">
                  <button onClick={createDSR} disabled={saving || !dsrForm.data_subject_name || !dsrForm.data_subject_email}
                    className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-medium">
                    {saving ? 'Creating...' : 'Create Request'}
                  </button>
                  <button onClick={() => setShowCreateDSR(false)} className="px-4 py-2 rounded-lg border border-gray-600 text-sm text-gray-300">Cancel</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Report Breach Modal */}
      {showCreateBreach && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-xl w-full max-w-md border border-gray-600">
            <div className="p-6">
              <div className="flex justify-between items-center mb-5">
                <h3 className="font-bold text-lg text-red-400">Report Data Breach</h3>
                <button onClick={() => setShowCreateBreach(false)} className="text-gray-400 hover:text-white text-xl">✕</button>
              </div>
              <p className="text-xs text-yellow-300 bg-yellow-900/20 border border-yellow-700 rounded p-2 mb-4">
                ⚠️ GDPR Art. 33 requires supervisory authority notification within 72 hours of discovery.
              </p>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Description *</label>
                  <textarea value={breachForm.description} onChange={e => setBreachForm(p => ({ ...p, description: e.target.value }))}
                    rows={3} placeholder="What data was affected? How did the breach occur?"
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white resize-none" />
                </div>
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Risk Level</label>
                  <select value={breachForm.risk_level} onChange={e => setBreachForm(p => ({ ...p, risk_level: e.target.value }))}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white">
                    {['low', 'medium', 'high', 'critical'].map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Estimated Subjects Affected</label>
                  <input type="number" min={0} value={breachForm.estimated_subjects_affected}
                    onChange={e => setBreachForm(p => ({ ...p, estimated_subjects_affected: Number(e.target.value) }))}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white" />
                </div>
                <div className="flex gap-3 pt-2">
                  <button onClick={createBreach} disabled={saving || !breachForm.description}
                    className="flex-1 bg-red-700 hover:bg-red-600 disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-medium">
                    {saving ? 'Reporting...' : 'Report Breach'}
                  </button>
                  <button onClick={() => setShowCreateBreach(false)} className="px-4 py-2 rounded-lg border border-gray-600 text-sm text-gray-300">Cancel</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
