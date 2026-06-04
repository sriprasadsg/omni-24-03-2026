import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

interface KBDoc {
  id: string;
  title: string;
  source: string;
  tags: string[];
  createdAt: string;
  snippet?: string;
  relevance?: number;
}

interface SearchResult extends KBDoc {
  snippet: string;
  relevance: number;
}

export default function KnowledgeBaseDashboard() {
  const [docs, setDocs] = useState<KBDoc[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [showIngest, setShowIngest] = useState(false);
  const [ingestForm, setIngestForm] = useState({ title: '', content: '', source: '', tags: '' });
  const [ingesting, setIngesting] = useState(false);
  const [activeTab, setActiveTab] = useState<'browse' | 'search'>('browse');
  const [total, setTotal] = useState(0);

  useEffect(() => { loadDocs(); }, []);

  async function loadDocs() {
    try {
      const r = await authFetch('/api/knowledge/docs');
      const d = await r.json();
      setDocs(d.docs || []);
      setTotal(d.count || 0);
    } catch (e) { console.error(e); }
  }

  async function search() {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const r = await authFetch('/api/knowledge/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, limit: 20 }),
      });
      const d = await r.json();
      setResults(d.results || []);
      setActiveTab('search');
    } finally { setSearching(false); }
  }

  async function ingest() {
    setIngesting(true);
    try {
      const r = await authFetch('/api/knowledge/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: ingestForm.title,
          content: ingestForm.content,
          source: ingestForm.source || 'manual',
          tags: ingestForm.tags.split(',').map(t => t.trim()).filter(Boolean),
        }),
      });
      if (r.ok) {
        loadDocs();
        setShowIngest(false);
        setIngestForm({ title: '', content: '', source: '', tags: '' });
      } else {
        const d = await r.json();
        showToast(d.detail || 'Failed to ingest', 'error');
      }
    } finally { setIngesting(false); }
  }

  async function deleteDoc(id: string) {
    if (!confirm('Delete this document from the knowledge base?')) return;
    await authFetch(`/api/knowledge/docs/${id}`, { method: 'DELETE' });
    loadDocs();
    setResults(prev => prev.filter(r => r.id !== id));
  }

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Knowledge Base</h1>
          <p className="text-gray-400 text-sm mt-1">RAG-powered knowledge store — ingest docs, runbooks, policies, and query them with AI</p>
        </div>
        <button onClick={() => setShowIngest(true)} className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm font-medium">
          + Ingest Document
        </button>
      </div>

      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 mb-6">
        <div className="flex gap-3">
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && search()}
            placeholder="Search knowledge base (semantic + full-text)…"
            className="flex-1 bg-gray-700 border border-gray-600 rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-500"
          />
          <button onClick={search} disabled={searching || !query.trim()}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-5 py-2.5 rounded-lg text-sm font-medium">
            {searching ? 'Searching…' : 'Search'}
          </button>
        </div>
      </div>

      <div className="flex gap-2 mb-4">
        <button onClick={() => setActiveTab('browse')}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium ${activeTab === 'browse' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}>
          All Documents ({total})
        </button>
        {results.length > 0 && (
          <button onClick={() => setActiveTab('search')}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium ${activeTab === 'search' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}>
            Search Results ({results.length})
          </button>
        )}
      </div>

      {activeTab === 'browse' && (
        docs.length === 0 ? (
          <div className="text-center py-20 text-gray-500 bg-gray-800 rounded-xl border border-gray-700">
            <div className="text-5xl mb-4">📚</div>
            <p className="text-lg">No documents in knowledge base</p>
            <p className="text-sm mt-2">Ingest runbooks, security policies, playbooks, and threat intel to enable AI-powered Q&A</p>
            <button onClick={() => setShowIngest(true)} className="mt-4 bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded-lg text-sm">
              Ingest First Document
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            {docs.map(doc => (
              <div key={doc.id} className="bg-gray-800 rounded-xl px-5 py-4 border border-gray-700 flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <h3 className="font-medium truncate">{doc.title || 'Untitled'}</h3>
                  <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
                    <span>Source: {doc.source}</span>
                    <span>Added: {new Date(doc.createdAt).toLocaleDateString()}</span>
                  </div>
                  {doc.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {doc.tags.map(t => (
                        <span key={t} className="text-xs bg-blue-900/30 text-blue-300 border border-blue-800 px-2 py-0.5 rounded">{t}</span>
                      ))}
                    </div>
                  )}
                </div>
                <button onClick={() => deleteDoc(doc.id)}
                  className="text-gray-600 hover:text-red-400 text-xs shrink-0">Delete</button>
              </div>
            ))}
          </div>
        )
      )}

      {activeTab === 'search' && (
        <div className="space-y-3">
          <p className="text-sm text-gray-400">{results.length} results for "<span className="text-white">{query}</span>"</p>
          {results.map((res, i) => (
            <div key={res.id || i} className="bg-gray-800 rounded-xl p-5 border border-gray-700">
              <div className="flex items-start justify-between mb-2">
                <h3 className="font-medium">{res.title || 'Untitled'}</h3>
                <span className="text-xs text-green-400 bg-green-900/30 border border-green-800 px-2 py-0.5 rounded shrink-0 ml-3">
                  {Math.round((1 - (res.relevance || 0)) * 100)}% match
                </span>
              </div>
              <p className="text-sm text-gray-300 leading-relaxed">{res.snippet}</p>
              <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
                <span>Source: {res.source}</span>
                {res.tags?.length > 0 && <span>Tags: {res.tags.join(', ')}</span>}
              </div>
            </div>
          ))}
        </div>
      )}

      {showIngest && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-xl w-full max-w-2xl border border-gray-600 max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex justify-between items-center mb-5">
                <h3 className="font-bold text-lg">Ingest Document</h3>
                <button onClick={() => setShowIngest(false)} className="text-gray-400 hover:text-white">✕</button>
              </div>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Title</label>
                  <input value={ingestForm.title} onChange={e => setIngestForm(p => ({ ...p, title: e.target.value }))}
                    placeholder="e.g. Incident Response Runbook v2"
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white" />
                </div>
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Source</label>
                  <input value={ingestForm.source} onChange={e => setIngestForm(p => ({ ...p, source: e.target.value }))}
                    placeholder="e.g. confluence, github, manual"
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white" />
                </div>
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Tags (comma-separated)</label>
                  <input value={ingestForm.tags} onChange={e => setIngestForm(p => ({ ...p, tags: e.target.value }))}
                    placeholder="runbook, ir, p1-response"
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white" />
                </div>
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Content *</label>
                  <textarea value={ingestForm.content} onChange={e => setIngestForm(p => ({ ...p, content: e.target.value }))}
                    rows={10} placeholder="Paste document content here…"
                    className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white resize-none font-mono text-xs" />
                </div>
                <div className="flex gap-3 pt-2">
                  <button onClick={ingest} disabled={ingesting || !ingestForm.content.trim()}
                    className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-medium">
                    {ingesting ? 'Ingesting…' : 'Ingest Document'}
                  </button>
                  <button onClick={() => setShowIngest(false)} className="px-4 py-2 rounded-lg border border-gray-600 text-sm">Cancel</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
