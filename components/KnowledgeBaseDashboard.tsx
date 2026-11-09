import React, { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';
import { fetchGaps } from '../services/serviceDesk/knowledgeApi';
import type { KbDocFlags, KnowledgeGapGroup } from '../services/serviceDesk/types';
import { HealthNotice } from './serviceDesk/deskUi';
import { ArticleEditDialog, type EditableArticle } from './serviceDesk/ArticleEditDialog';
import { EditArticleButton, HelpDeskChips, HelpDeskToggle, SharedReferenceLine } from './serviceDesk/HelpDeskToggle';
import { StarterArticlesDialog } from './serviceDesk/StarterArticlesDialog';
import { SECONDARY_BUTTON } from './serviceDesk/deskUi';
import { KnowledgeGapsTab } from './serviceDesk/KnowledgeGapsTab';
import { GAPS, KB, fill } from './serviceDesk/serviceDeskCopy';
import { InfoIcon, SparklesIcon } from './icons';

interface KBDoc {
  id: string;
  title: string;
  source: string;
  tags: string[];
  createdAt: string;
  snippet?: string;
  relevance?: number;
  /** Phase 85: the service desk may quote this article (never true on a platform article). */
  helpdesk?: boolean;
  starterKey?: string | null;
  updatedAt?: string;
  /** "global" marks a platform reference article. */
  tenantId?: string;
}

/** What the server says about the caller and the desk; with an older server every flag reads off. */
const NO_FLAGS: KbDocFlags = { canManageArticles: false, canSeeGaps: false, helpdeskCount: 0, starterMissing: 0, deskOff: true };

const tabClass = (active: boolean) =>
  `px-3 py-1.5 rounded-lg text-sm font-medium ${active ? 'bg-blue-600 text-white' : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'}`;

interface SearchResult extends KBDoc {
  snippet: string;
  relevance: number;
}

/** The Knowledge gaps tab: amber text while groups are open, so the need for an article is seen from the other tabs. */
const gapTabClass = (active: boolean, open: boolean) => {
  if (!open) return tabClass(active);
  return `px-3 py-1.5 rounded-lg text-sm font-medium ${active ? 'bg-amber-100 text-amber-900 dark:bg-amber-400/20 dark:text-amber-200' : 'bg-white dark:bg-gray-800 text-amber-700 dark:text-amber-300 hover:text-amber-900 dark:hover:text-amber-200'}`;
};

export default function KnowledgeBaseDashboard() {
  const [docs, setDocs] = useState<KBDoc[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [showIngest, setShowIngest] = useState(false);
  const [ingestForm, setIngestForm] = useState({ title: '', content: '', source: '', tags: '' });
  const [ingesting, setIngesting] = useState(false);
  const [activeTab, setActiveTab] = useState<'browse' | 'search' | 'helpdesk' | 'gaps'>('browse');
  const [total, setTotal] = useState(0);
  const [flags, setFlags] = useState<KbDocFlags>(NO_FLAGS);
  const [editing, setEditing] = useState<EditableArticle | null>(null);
  const [showStarters, setShowStarters] = useState(false);
  const [gapCount, setGapCount] = useState<number | null>(null);
  const [gapsKey, setGapsKey] = useState(0);
  const [writing, setWriting] = useState<KnowledgeGapGroup | null>(null);

  useEffect(() => { loadDocs(); }, []);

  // The Knowledge gaps tab label carries the open count: read it once, when the server first says this person may see gaps.
  useEffect(() => {
    if (!flags.canSeeGaps) return undefined;
    let cancelled = false;
    fetchGaps(false).then(v => { if (!cancelled) setGapCount(v.groups.filter(g => g.status === 'open').length); }).catch(() => { /* the tab shows its own error */ });
    return () => { cancelled = true; };
  }, [flags.canSeeGaps]);
  const onGapCount = useCallback((n: number) => setGapCount(n), []);

  async function loadDocs() {
    try {
      const r = await authFetch('/api/knowledge/docs');
      const d = await r.json();
      setDocs(d.docs || []);
      setTotal(d.count || 0);
      setFlags({
        canManageArticles: d.canManageArticles === true,
        canSeeGaps: d.canSeeGaps === true,
        helpdeskCount: Number(d.helpdeskCount) || 0,
        starterMissing: Number(d.starterMissing) || 0,
        deskOff: d.deskOff === true,
      });
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

  /** The Help desk switch saved: show the new state and move the count by one without asking the server again. */
  function markChanged(id: string, next: boolean) {
    setDocs(prev => prev.map(d => (d.id === id ? { ...d, helpdesk: next } : d)));
    setFlags(prev => ({ ...prev, helpdeskCount: Math.max(0, prev.helpdeskCount + (next ? 1 : -1)) }));
  }

  const manage = flags.canManageArticles;
  const shown = activeTab === 'helpdesk' ? docs.filter(d => d.helpdesk) : docs;

  return (
    <div className="p-6 bg-transparent dark:bg-gray-900 min-h-screen text-gray-900 dark:text-white">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Knowledge Base</h1>
          <p className="text-gray-600 dark:text-gray-400 text-sm mt-1">RAG-powered knowledge store — ingest docs, runbooks, policies, and query them with AI</p>
          {manage && (
            flags.helpdeskCount === 0 && !flags.deskOff ? (
              <div className="mt-2 max-w-3xl">
                <HealthNotice tone="amber" role="status"><p>{KB.noHelpdeskArticles}</p></HealthNotice>
              </div>
            ) : (
              <p className="mt-2 flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                <InfoIcon size={12} aria-hidden="true" />
                {flags.helpdeskCount === 1 ? KB.readinessOne : fill(KB.readiness, { k: flags.helpdeskCount })}
              </p>
            )
          )}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {manage && (flags.starterMissing > 0 ? (
            <button type="button" className={SECONDARY_BUTTON} onClick={() => setShowStarters(true)}>
              <SparklesIcon size={16} aria-hidden="true" />
              {KB.addStarters}
            </button>
          ) : (
            <span className="text-xs text-gray-500 dark:text-gray-400">{KB.startersAdded}</span>
          ))}
          <button onClick={() => setShowIngest(true)} className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm font-medium text-white">
            + Ingest Document
          </button>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-200 dark:border-gray-700 mb-6">
        <div className="flex gap-3">
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && search()}
            placeholder="Search knowledge base (semantic + full-text)…"
            className="flex-1 bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2.5 text-sm text-gray-900 dark:text-white placeholder-gray-500"
          />
          <button onClick={search} disabled={searching || !query.trim()}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-5 py-2.5 rounded-lg text-sm font-medium text-white">
            {searching ? 'Searching…' : 'Search'}
          </button>
        </div>
      </div>

      <div className="flex gap-2 mb-4">
        <button onClick={() => setActiveTab('browse')} className={tabClass(activeTab === 'browse')}>
          {fill(KB.filterAll, { total })}
        </button>
        {manage && (
          <button onClick={() => setActiveTab('helpdesk')} className={tabClass(activeTab === 'helpdesk')}>
            {fill(KB.filterHelpDesk, { k: flags.helpdeskCount })}
          </button>
        )}
        {flags.canSeeGaps && (
          <button onClick={() => setActiveTab('gaps')} className={gapTabClass(activeTab === 'gaps', (gapCount ?? 0) > 0)}>
            {gapCount === null ? GAPS.heading : fill(GAPS.tab, { n: gapCount })}
          </button>
        )}
        {results.length > 0 && (
          <button onClick={() => setActiveTab('search')}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium ${activeTab === 'search' ? 'bg-blue-600 text-white' : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'}`}>
            Search Results ({results.length})
          </button>
        )}
      </div>

      {activeTab === 'gaps' && flags.canSeeGaps && (
        <KnowledgeGapsTab refreshKey={gapsKey} onOpenCount={onGapCount} onWrite={setWriting} />
      )}

      {(activeTab === 'browse' || activeTab === 'helpdesk') && (
        shown.length === 0 && activeTab === 'helpdesk' ? (
          <p className="py-10 text-center text-sm text-gray-600 dark:text-gray-400">{KB.filterHelpDeskEmpty}</p>
        ) : docs.length === 0 ? (
          <div className="text-center py-20 text-gray-500 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
            <div className="text-5xl mb-4">📚</div>
            <p className="text-lg">No documents in knowledge base</p>
            <p className="text-sm mt-2">Ingest runbooks, security policies, playbooks, and threat intel to enable AI-powered Q&A</p>
            <button onClick={() => setShowIngest(true)} className="mt-4 bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded-lg text-sm text-white">
              Ingest First Document
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            {shown.map(doc => {
              const platform = doc.tenantId === 'global';
              return (
              <div key={doc.id} className="bg-white dark:bg-gray-800 rounded-xl px-5 py-4 border border-gray-200 dark:border-gray-700 flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-medium break-words">{doc.title || 'Untitled'}</h3>
                    <HelpDeskChips helpdesk={doc.helpdesk === true} starter={!!doc.starterKey} platform={platform} />
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-gray-600 dark:text-gray-400">
                    <span>Source: {doc.source}</span>
                    <span>Added: {new Date(doc.createdAt).toLocaleDateString()}</span>
                  </div>
                  {doc.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {doc.tags.map(t => (
                        <span key={t} className="text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800 px-2 py-0.5 rounded">{t}</span>
                      ))}
                    </div>
                  )}
                  {manage && platform && <div className="mt-2"><SharedReferenceLine /></div>}
                </div>
                <div className="flex shrink-0 flex-col items-end gap-2">
                  {manage && !platform && (
                    <HelpDeskToggle docId={doc.id} title={doc.title || 'Untitled'} checked={doc.helpdesk === true}
                      onChanged={next => markChanged(doc.id, next)} />
                  )}
                  {manage && !platform && (
                    <EditArticleButton title={doc.title || 'Untitled'}
                      onEdit={() => setEditing({ id: doc.id, title: doc.title, tags: doc.tags ?? [], starterKey: doc.starterKey })} />
                  )}
                  <button onClick={() => deleteDoc(doc.id)}
                    className="text-gray-600 hover:text-red-600 dark:hover:text-red-400 text-xs shrink-0">Delete</button>
                </div>
              </div>
              );
            })}
          </div>
        )
      )}

      {activeTab === 'search' && (
        <div className="space-y-3">
          <p className="text-sm text-gray-600 dark:text-gray-400">{results.length} results for "<span className="text-white">{query}</span>"</p>
          {results.map((res, i) => (
            <div key={res.id || i} className="bg-white dark:bg-gray-800 rounded-xl p-5 border border-gray-200 dark:border-gray-700">
              <div className="flex items-start justify-between mb-2">
                <h3 className="font-medium">{res.title || 'Untitled'}</h3>
                <span className="text-xs text-green-600 dark:text-green-400 bg-green-100 dark:bg-green-900/30 border border-green-200 dark:border-green-800 px-2 py-0.5 rounded shrink-0 ml-3">
                  {Math.round((1 - (res.relevance || 0)) * 100)}% match
                </span>
              </div>
              <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">{res.snippet}</p>
              <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
                <span>Source: {res.source}</span>
                {res.tags?.length > 0 && <span>Tags: {res.tags.join(', ')}</span>}
              </div>
            </div>
          ))}
        </div>
      )}

      {showStarters && (
        <StarterArticlesDialog missing={flags.starterMissing} onClose={() => setShowStarters(false)}
          onDone={() => { setShowStarters(false); loadDocs(); }} />
      )}

      {editing && (
        <ArticleEditDialog mode="edit" doc={editing} onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); loadDocs(); }} />
      )}

      {writing && (
        <ArticleEditDialog mode="write" initialTitle={writing.question} gapGroupId={writing.id} onClose={() => setWriting(null)}
          onSaved={() => { setWriting(null); loadDocs(); setGapsKey(k => k + 1); }} />
      )}

      {showIngest && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-xl w-full max-w-2xl border border-gray-300 dark:border-gray-600 max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex justify-between items-center mb-5">
                <h3 className="font-bold text-lg">Ingest Document</h3>
                <button onClick={() => setShowIngest(false)} className="text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">✕</button>
              </div>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-gray-600 dark:text-gray-400 block mb-1">Title</label>
                  <input value={ingestForm.title} onChange={e => setIngestForm(p => ({ ...p, title: e.target.value }))}
                    placeholder="e.g. Incident Response Runbook v2"
                    className="w-full bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded px-3 py-2 text-sm text-gray-900 dark:text-white" />
                </div>
                <div>
                  <label className="text-sm text-gray-600 dark:text-gray-400 block mb-1">Source</label>
                  <input value={ingestForm.source} onChange={e => setIngestForm(p => ({ ...p, source: e.target.value }))}
                    placeholder="e.g. confluence, github, manual"
                    className="w-full bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded px-3 py-2 text-sm text-gray-900 dark:text-white" />
                </div>
                <div>
                  <label className="text-sm text-gray-600 dark:text-gray-400 block mb-1">Tags (comma-separated)</label>
                  <input value={ingestForm.tags} onChange={e => setIngestForm(p => ({ ...p, tags: e.target.value }))}
                    placeholder="runbook, ir, p1-response"
                    className="w-full bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded px-3 py-2 text-sm text-gray-900 dark:text-white" />
                </div>
                <div>
                  <label className="text-sm text-gray-600 dark:text-gray-400 block mb-1">Content *</label>
                  <textarea value={ingestForm.content} onChange={e => setIngestForm(p => ({ ...p, content: e.target.value }))}
                    rows={10} placeholder="Paste document content here…"
                    className="w-full bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded px-3 py-2 text-sm text-gray-900 dark:text-white resize-none font-mono text-xs" />
                </div>
                <div className="flex gap-3 pt-2">
                  <button onClick={ingest} disabled={ingesting || !ingestForm.content.trim()}
                    className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-medium text-white">
                    {ingesting ? 'Ingesting…' : 'Ingest Document'}
                  </button>
                  <button onClick={() => setShowIngest(false)} className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 text-sm">Cancel</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
