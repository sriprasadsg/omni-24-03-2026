import React, { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';
import { FileTextIcon } from './icons/FileTextIcon';

interface GovernanceDocument {
  id: string;
  title: string;
  status: 'draft' | 'pending_approval' | 'approved' | 'published';
  created_at: string;
  signatures?: any[];
  current_version?: number;
}

type Tab = 'all' | 'pending' | 'signed';

export const GovernanceDocumentsDashboard: React.FC = () => {
  const [tab, setTab] = useState<Tab>('all');
  const [documents, setDocuments] = useState<GovernanceDocument[]>([]);
  const [loading, setLoading] = useState(false);

  // Form states
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newDocTitle, setNewDocTitle] = useState('');
  const [newDocContent, setNewDocContent] = useState('');

  const [showSignModal, setShowSignModal] = useState<{ open: boolean; docId: string | null }>({ open: false, docId: null });
  const [signTypedName, setSignTypedName] = useState('');
  const [signConsent, setSignConsent] = useState(false);

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const url = `/api/governance/documents${tab === 'pending' ? '?status=pending_approval' : ''}${tab === 'signed' ? '?signatures.exists=true' : ''}`;
      const res = await authFetch(url);
      if (!res.ok) throw new Error();
      const body = await res.json();
      setDocuments(Array.isArray(body.items) ? body.items : Array.isArray(body) ? body : []);
    } catch { showToast('Failed to load documents', 'error'); }
    finally { setLoading(false); }
  }, [tab]);

  useEffect(() => { fetchDocuments(); }, [fetchDocuments]);

  const createDocument = async () => {
    if (!newDocTitle.trim()) { showToast('Title required', 'error'); return; }
    try {
      const res = await authFetch('/api/governance/documents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newDocTitle, content: newDocContent, doc_type: 'policy' })
      });
      if (!res.ok) { showToast('Failed to create document', 'error'); return; }
      showToast('Document created', 'success');
      setShowCreateForm(false);
      setNewDocTitle(''); setNewDocContent('');
      fetchData();
    } catch { showToast('Failed', 'error'); }
  };

  const addVersion = async (docId: string, content: string) => {
    try {
      const res = await authFetch(`/api/governance/documents/${docId}/new-version`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
      });
      if (!res.ok) { showToast('Failed to add version', 'error'); return; }
      showToast('Version added', 'success');
      fetchData();
    } catch { showToast('Failed', 'error'); }
  };

  const submitForApproval = async (docId: string) => {
    try {
      const res = await authFetch(`/api/governance/documents/${docId}/submit-for-approval`, { method: 'POST' });
      if (!res.ok) { showToast('Failed to submit', 'error'); return; }
      showToast('Submitted for approval', 'success');
      fetchData();
    } catch { showToast('Failed', 'error'); }
  };

  const publishDocument = async (docId: string) => {
    try {
      const res = await authFetch(`/api/governance/documents/${docId}/publish`, { method: 'POST' });
      if (!res.ok) { showToast('Failed to publish', 'error'); return; }
      showToast('Published', 'success');
      fetchData();
    } catch { showToast('Failed', 'error'); }
  };

  const signDocument = async (docId: string) => {
    if (!signTypedName.trim()) { showToast('Name required', 'error'); return; }
    if (!signConsent) { showToast('Consent required', 'error'); return; }
    try {
      const res = await authFetch(`/api/governance/documents/${docId}/sign`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ typed_name: signTypedName, consent: true })
      });
      if (!res.ok) { showToast('Failed to sign', 'error'); return; }
      showToast('Signed', 'success');
      setShowSignModal({ open: false, docId: null });
      setSignTypedName(''); setSignConsent(false);
      fetchData();
    } catch { showToast('Failed', 'error'); }
  };

  const exportPdf = async (docId: string) => {
    try {
      const res = await authFetch(`/api/governance/documents/${docId}/export-signed-pdf`);
      if (!res.ok) { showToast('Failed to export PDF', 'error'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `${docId}-signed.pdf`; a.click(); URL.revokeObjectURL(url);
      showToast('PDF exported', 'success');
    } catch { showToast('Failed', 'error'); }
  };

  const TABS: { key: Tab; label: string }[] = [
    { key: 'all', label: 'All Documents' },
    { key: 'pending', label: 'Pending Approval' },
    { key: 'signed', label: 'Signed' },
  ];

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">Governance Documents</h2>
        <button
          onClick={() => setShowCreateForm(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >Create Document</button>
      </div>

      {showCreateForm && (
        <div className="border p-4 rounded bg-gray-50 dark:bg-gray-800 space-y-3">
          <h3 className="font-medium">New Document</h3>
          <input
            type="text"
            value={newDocTitle}
            onChange={(e) => setNewDocTitle(e.target.value)}
            placeholder="Title"
            className="w-full px-3 py-2 border rounded"
          />
          <textarea
            value={newDocContent}
            onChange={(e) => setNewDocContent(e.target.value)}
            placeholder="Content"
            className="w-full px-3 py-2 border rounded h-24"
          />
          <div className="flex gap-2">
            <button onClick={createDocument} className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700">Create</button>
            <button onClick={() => setShowCreateForm(false)} className="px-4 py-2 border rounded">Cancel</button>
          </div>
        </div>
      )}

      <div className="flex gap-2 border-b">
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 ${tab === t.key ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}
          >{t.label}</button>
        ))}
      </div>

      {loading && <p className="text-sm text-gray-400">Loading...</p>}

      {documents.map(doc => (
        <div key={doc.id} className="border rounded p-4 space-y-2 bg-white dark:bg-gray-900">
          <div className="flex justify-between items-start">
            <h3 className="font-semibold flex items-center gap-2">
              <FileTextIcon className="w-4 h-4" /> {doc.title}
            </h3>
            <span className={`text-xs px-2 py-1 rounded ${
              doc.status === 'published' ? 'bg-green-100 text-green-800' :
              doc.status === 'pending_approval' ? 'bg-yellow-100 text-yellow-800' :
              doc.status === 'draft' ? 'bg-gray-100 text-gray-800' :
              'bg-blue-100 text-blue-800'}`}>{
                doc.status === 'published' ? 'Published' :
                doc.status === 'pending_approval' ? 'Pending Approval' :
                doc.status === 'draft' ? 'Draft' :
                doc.status
            }</span>
          </div>
          <p className="text-xs text-gray-500">Created: {new Date(doc.created_at).toLocaleString()}</p>
          {tab === 'all' && (
            <div className="flex gap-2">
              {doc.status === 'draft' && (
                <button onClick={() => addVersion(doc.id, '')} className="text-sm text-blue-600 hover:underline">+ Version</button>
              )}
              {doc.status === 'draft' && (
                <button onClick={() => submitForApproval(doc.id)} className="text-sm text-blue-600 hover:underline">Submit for Approval</button>
              )}
              {doc.status === 'pending_approval' && (
                <button onClick={() => publishDocument(doc.id)} className="text-sm text-green-600 hover:underline">Publish</button>
              )}
              {doc.status === 'published' && (
                <button onClick={() => setShowSignModal({ open: true, docId: doc.id })} className="text-sm text-purple-600 hover:underline">Sign</button>
              )}
              {doc.status === 'published' && doc.signatures?.length > 0 && (
                <button onClick={() => exportPdf(doc.id)} className="text-sm text-orange-600 hover:underline">Export PDF</button>
              )}
            </div>
          )}
          {tab === 'pending' && doc.status === 'pending_approval' && (
            <button onClick={() => publishDocument(doc.id)} className="text-sm text-green-600 hover:underline">Publish</button>
          )}
          {tab === 'signed' && doc.signatures?.length > 0 && (
            <div className="text-xs text-gray-600">
              Signed by: {doc.signatures[0].typed_name} on {new Date(doc.signatures[0].signed_at).toLocaleDateString()}
            </div>
          )}
        </div>
      ))}

      {showSignModal.open && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-900 p-6 rounded-lg space-y-4 max-w-md w-full">
            <h3 className="text-lg font-semibold">Sign Document</h3>
            <p className="text-sm text-gray-600">Enter your typed name and confirm consent.</p>
            <input
              type="text"
              value={signTypedName}
              onChange={(e) => setSignTypedName(e.target.value)}
              placeholder="Full Name"
              className="w-full px-3 py-2 border rounded"
            />
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={signConsent} onChange={(e) => setSignConsent(e.target.checked)} />
              I agree this constitutes my legal signature
            </label>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowSignModal({ open: false, docId: null })} className="px-4 py-2 border rounded">Cancel</button>
              <button onClick={() => signDocument(showSignModal.docId!)} className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700">Sign</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};