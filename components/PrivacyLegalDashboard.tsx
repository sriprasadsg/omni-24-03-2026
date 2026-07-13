import React, { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

type Tab = 'tia' | 'lia' | 'notices' | 'contracts';

interface TIARecord { id?: string; transfer_name: string; data_categories: string[]; safeguards?: string; source_country: string; destination_country: string; legal_basis: string; risk_level: string; status?: string; }
interface LIARecord { id?: string; purpose: string; necessity_test: string; balancing_test: string; outcome: string; data_subjects: string; }
interface NoticeRecord { id?: string; title: string; content_html: string; effective_date: string; applies_to: string; current_version?: number; }
interface ContractRecord { id?: string; vendor_name: string; type: string; status: string; expiry_date: string; parties: string[]; }

export const PrivacyLegalDashboard: React.FC = () => {
  const [tab, setTab] = useState<Tab>('tia');
  const [loading, setLoading] = useState(false);
  // TIA state
  const [tiaItems, setTiaItems] = useState<TIARecord[]>([]);
  const [showTiaForm, setShowTiaForm] = useState(false);
  const [tiaForm, setTiaForm] = useState<Partial<TIARecord>>({});
  // LIA state
  const [liaItems, setLiaItems] = useState<LIARecord[]>([]);
  const [showLiaForm, setShowLiaForm] = useState(false);
  const [liaForm, setLiaForm] = useState<Partial<LIARecord>>({});
  // Notices state
  const [noticeItems, setNoticeItems] = useState<NoticeRecord[]>([]);
  const [showNoticeForm, setShowNoticeForm] = useState(false);
  const [noticeForm, setNoticeForm] = useState<Partial<NoticeRecord>>({});
  // Contracts state
  const [contractItems, setContractItems] = useState<ContractRecord[]>([]);
  const [showContractForm, setShowContractForm] = useState(false);
  const [contractForm, setContractForm] = useState<Partial<ContractRecord>>({});
  const [expiring, setExpiring] = useState<ContractRecord[]>([]);

  const fetchJson = async (url: string) => {
    const res = await authFetch(url);
    const body = await res.json();
    if (!res.ok) { throw new Error(body?.detail || `Request failed: ${res.status}`); }
    return body;
  };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      if (tab === 'tia') { const r = await fetchJson('/api/privacy/tia'); setTiaItems(r.items || []); }
      if (tab === 'lia') { const r = await fetchJson('/api/privacy/lia'); setLiaItems(r.items || []); }
      if (tab === 'notices') { const r = await fetchJson('/api/privacy/notices'); setNoticeItems(r.items || []); }
      if (tab === 'contracts') {
        const r = await fetchJson('/api/privacy/contracts'); setContractItems(r.items || []);
        const e = await fetchJson('/api/privacy/contracts/expiring'); setExpiring(e.items || []);
      }
    } catch { showToast('Failed to load data', 'error'); }
    finally { setLoading(false); }
  }, [tab]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const submitTia = async () => { try { const res = await authFetch('/api/privacy/tia', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(tiaForm) }); const body = await res.json(); if (!res.ok) { showToast(body?.detail || 'Failed to create TIA', 'error'); return; } showToast('TIA created', 'success'); setShowTiaForm(false); setTiaForm({}); fetchData(); } catch { showToast('Failed', 'error'); } };
  const submitLia = async () => { try { const res = await authFetch('/api/privacy/lia', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(liaForm) }); const body = await res.json(); if (!res.ok) { showToast(body?.detail || 'Failed to create LIA', 'error'); return; } showToast('LIA created', 'success'); setShowLiaForm(false); setLiaForm({}); fetchData(); } catch { showToast('Failed', 'error'); } };
  const submitNotice = async () => { try { const res = await authFetch('/api/privacy/notices', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(noticeForm) }); const body = await res.json(); if (!res.ok) { showToast(body?.detail || 'Failed to create notice', 'error'); return; } showToast('Notice created', 'success'); setShowNoticeForm(false); setNoticeForm({}); fetchData(); } catch { showToast('Failed', 'error'); } };
  const submitContract = async () => { try { const res = await authFetch('/api/privacy/contracts', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(contractForm) }); const body = await res.json(); if (!res.ok) { showToast(body?.detail || 'Failed to create contract', 'error'); return; } showToast('Contract created', 'success'); setShowContractForm(false); setContractForm({}); fetchData(); } catch { showToast('Failed', 'error'); } };

  const TABS: { key: Tab; label: string }[] = [
    { key: 'tia', label: 'TIA' }, { key: 'lia', label: 'LIA' },
    { key: 'notices', label: 'Notices' }, { key: 'contracts', label: 'Contracts' },
  ];

  return (
    <div className="space-y-4">
      {/* Tab bar */}
      <div className="flex gap-1 border-b dark:border-gray-700">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium rounded-t ${tab === t.key ? 'bg-white dark:bg-gray-800 border border-b-0 dark:border-gray-600 text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}>{t.label}</button>
        ))}
      </div>

      {loading && <p className="text-sm text-gray-400">Loading...</p>}

      {/* TIA Tab */}
      {tab === 'tia' && (
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <h3 className="text-sm font-semibold">Transfer Impact Assessments</h3>
            <button onClick={() => setShowTiaForm(!showTiaForm)} className="px-3 py-1 text-xs bg-blue-600 text-white rounded">{showTiaForm ? 'Cancel' : '+ New TIA'}</button>
          </div>
          {showTiaForm && (
            <div className="grid grid-cols-2 gap-2 p-3 bg-gray-50 dark:bg-gray-800 rounded text-xs">
              <input placeholder="Transfer name" className="p-1 border rounded dark:bg-gray-700" onChange={e => setTiaForm({...tiaForm, transfer_name: e.target.value})} />
              <input placeholder="Source country" className="p-1 border rounded dark:bg-gray-700" onChange={e => setTiaForm({...tiaForm, source_country: e.target.value})} />
              <input placeholder="Destination country" className="p-1 border rounded dark:bg-gray-700" onChange={e => setTiaForm({...tiaForm, destination_country: e.target.value})} />
              <input placeholder="Legal basis" className="p-1 border rounded dark:bg-gray-700" onChange={e => setTiaForm({...tiaForm, legal_basis: e.target.value})} />
              <select className="p-1 border rounded dark:bg-gray-700" onChange={e => setTiaForm({...tiaForm, risk_level: e.target.value})}>
                <option value="">Risk level</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
              </select>
              <input placeholder="Data categories (comma-separated)" className="p-1 border rounded dark:bg-gray-700 col-span-2" onChange={e => setTiaForm({...tiaForm, data_categories: e.target.value.split(',').map(v => v.trim()).filter(Boolean)})} />
              <input placeholder="Safeguards" className="p-1 border rounded dark:bg-gray-700 col-span-2" onChange={e => setTiaForm({...tiaForm, safeguards: e.target.value})} />
              <button onClick={submitTia} className="px-2 py-1 bg-blue-600 text-white rounded">Create</button>
            </div>
          )}
          {tiaItems.map((item, i) => (
            <div key={i} className="flex justify-between p-2 bg-white dark:bg-gray-800 rounded shadow-sm text-xs">
              <span>{item.transfer_name} — {item.source_country}→{item.destination_country}</span>
              <span className={`px-1.5 py-0.5 rounded ${item.risk_level === 'high' ? 'bg-red-100 text-red-700' : item.risk_level === 'medium' ? 'bg-amber-100 text-amber-700' : 'bg-green-100 text-green-700'}`}>{item.risk_level}</span>
            </div>
          ))}
          {!loading && tiaItems.length === 0 && <p className="text-xs text-gray-400 italic">No TIAs yet.</p>}
        </div>
      )}

      {/* LIA Tab */}
      {tab === 'lia' && (
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <h3 className="text-sm font-semibold">Legitimate Interest Assessments</h3>
            <button onClick={() => setShowLiaForm(!showLiaForm)} className="px-3 py-1 text-xs bg-blue-600 text-white rounded">{showLiaForm ? 'Cancel' : '+ New LIA'}</button>
          </div>
          {showLiaForm && (
            <div className="grid grid-cols-2 gap-2 p-3 bg-gray-50 dark:bg-gray-800 rounded text-xs">
              <input placeholder="Purpose" className="p-1 border rounded dark:bg-gray-700" onChange={e => setLiaForm({...liaForm, purpose: e.target.value})} />
              <input placeholder="Data subjects" className="p-1 border rounded dark:bg-gray-700" onChange={e => setLiaForm({...liaForm, data_subjects: e.target.value})} />
              <textarea placeholder="Necessity test" className="p-1 border rounded dark:bg-gray-700 col-span-2" rows={2} onChange={e => setLiaForm({...liaForm, necessity_test: e.target.value})} />
              <textarea placeholder="Balancing test" className="p-1 border rounded dark:bg-gray-700 col-span-2" rows={2} onChange={e => setLiaForm({...liaForm, balancing_test: e.target.value})} />
              <button onClick={submitLia} className="px-2 py-1 bg-blue-600 text-white rounded col-span-2">Create</button>
            </div>
          )}
          {liaItems.map((item, i) => (
            <div key={i} className="p-2 bg-white dark:bg-gray-800 rounded shadow-sm text-xs">
              <span className="font-medium">{item.purpose}</span> — {item.data_subjects}
            </div>
          ))}
          {!loading && liaItems.length === 0 && <p className="text-xs text-gray-400 italic">No LIAs yet.</p>}
        </div>
      )}

      {/* Notices Tab */}
      {tab === 'notices' && (
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <h3 className="text-sm font-semibold">Privacy Notices</h3>
            <button onClick={() => setShowNoticeForm(!showNoticeForm)} className="px-3 py-1 text-xs bg-blue-600 text-white rounded">{showNoticeForm ? 'Cancel' : '+ New Notice'}</button>
          </div>
          {showNoticeForm && (
            <div className="grid grid-cols-2 gap-2 p-3 bg-gray-50 dark:bg-gray-800 rounded text-xs">
              <input placeholder="Title" className="p-1 border rounded dark:bg-gray-700" onChange={e => setNoticeForm({...noticeForm, title: e.target.value})} />
              <input placeholder="Effective date" type="date" className="p-1 border rounded dark:bg-gray-700" onChange={e => setNoticeForm({...noticeForm, effective_date: e.target.value})} />
              <input placeholder="Applies to" className="p-1 border rounded dark:bg-gray-700" onChange={e => setNoticeForm({...noticeForm, applies_to: e.target.value})} />
              <textarea placeholder="Content (HTML)" className="p-1 border rounded dark:bg-gray-700 col-span-2" rows={3} onChange={e => setNoticeForm({...noticeForm, content_html: e.target.value})} />
              <button onClick={submitNotice} className="px-2 py-1 bg-blue-600 text-white rounded col-span-2">Create</button>
            </div>
          )}
          {noticeItems.map((item, i) => (
            <div key={i} className="p-2 bg-white dark:bg-gray-800 rounded shadow-sm text-xs">
              <div className="font-medium">{item.title} <span className="text-gray-400">v{item.current_version || 1}</span></div>
              <div className="text-gray-500">Effective: {item.effective_date} · Applies to: {item.applies_to}</div>
            </div>
          ))}
          {!loading && noticeItems.length === 0 && <p className="text-xs text-gray-400 italic">No notices yet.</p>}
        </div>
      )}

      {/* Contracts Tab */}
      {tab === 'contracts' && (
        <div className="space-y-2">
          {expiring.length > 0 && (
            <div className="p-2 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded text-xs text-amber-800 dark:text-amber-300">
              ⚠ {expiring.length} contract(s) expiring within 30 days
            </div>
          )}
          <div className="flex justify-between items-center">
            <h3 className="text-sm font-semibold">Contracts</h3>
            <button onClick={() => setShowContractForm(!showContractForm)} className="px-3 py-1 text-xs bg-blue-600 text-white rounded">{showContractForm ? 'Cancel' : '+ New Contract'}</button>
          </div>
          {showContractForm && (
            <div className="grid grid-cols-2 gap-2 p-3 bg-gray-50 dark:bg-gray-800 rounded text-xs">
              <input placeholder="Vendor name" className="p-1 border rounded dark:bg-gray-700" onChange={e => setContractForm({...contractForm, vendor_name: e.target.value})} />
              <select className="p-1 border rounded dark:bg-gray-700" onChange={e => setContractForm({...contractForm, type: e.target.value})}>
                <option value="">Type</option><option value="DPA">DPA</option><option value="MSA">MSA</option><option value="NDA">NDA</option><option value="SCC">SCC</option>
              </select>
              <select className="p-1 border rounded dark:bg-gray-700" onChange={e => setContractForm({...contractForm, status: e.target.value})}>
                <option value="">Status</option><option value="draft">Draft</option><option value="review">Review</option><option value="signed">Signed</option><option value="expired">Expired</option>
              </select>
              <input placeholder="Expiry date" type="date" className="p-1 border rounded dark:bg-gray-700" onChange={e => setContractForm({...contractForm, expiry_date: e.target.value})} />
              <input placeholder="Parties (comma-separated)" className="p-1 border rounded dark:bg-gray-700 col-span-2" onChange={e => setContractForm({...contractForm, parties: e.target.value.split(',').map(v => v.trim()).filter(Boolean)})} />
              <button onClick={submitContract} className="px-2 py-1 bg-blue-600 text-white rounded">Create</button>
            </div>
          )}
          {contractItems.map((item, i) => (
            <div key={i} className="flex justify-between p-2 bg-white dark:bg-gray-800 rounded shadow-sm text-xs">
              <div><span className="font-medium">{item.vendor_name}</span> — {item.type} · {item.status}</div>
              <span className="text-gray-500">Exp: {item.expiry_date}</span>
            </div>
          ))}
          {!loading && contractItems.length === 0 && <p className="text-xs text-gray-400 italic">No contracts yet.</p>}
        </div>
      )}
    </div>
  );
};
