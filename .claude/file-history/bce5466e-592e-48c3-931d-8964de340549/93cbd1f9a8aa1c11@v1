import React, { useState, useEffect, useRef } from 'react';
import { Search, Play, Save, Trash2, Code, Shield, Clock, Database } from 'lucide-react';

const API = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000';
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem('auth_token')}`, 'Content-Type': 'application/json' });

type Tab = 'hunt' | 'saved' | 'ioc' | 'templates';

interface HuntResult { [key: string]: unknown }
interface SavedQuery { id: string; name: string; description: string; category: string; last_run: string; run_count: number; query: string }
interface IocMatch { source: string; timestamp: string; details: string }
interface IocResult { match_count: number; matches: IocMatch[] }
interface Template { id: string; name: string; description: string; mitre_technique: string; query: string }

export default function AdvancedHuntingDashboard() {
  const [activeTab, setActiveTab] = useState<Tab>('hunt');
  const [query, setQuery] = useState('');
  const [timeRange, setTimeRange] = useState('24');
  const [limit, setLimit] = useState('100');
  const [results, setResults] = useState<HuntResult[]>([]);
  const [huntStats, setHuntStats] = useState<{ count: number; ms: number } | null>(null);
  const [huntLoading, setHuntLoading] = useState(false);
  const [huntError, setHuntError] = useState('');
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [saveDesc, setSaveDesc] = useState('');
  const [savedQueries, setSavedQueries] = useState<SavedQuery[]>([]);
  const [sqLoading, setSqLoading] = useState(false);
  const [iocValue, setIocValue] = useState('');
  const [iocType, setIocType] = useState('IP');
  const [iocResult, setIocResult] = useState<IocResult | null>(null);
  const [iocLoading, setIocLoading] = useState(false);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [tplLoading, setTplLoading] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (activeTab === 'saved') loadSavedQueries();
    if (activeTab === 'templates') loadTemplates();
  }, [activeTab]);

  const runHunt = async () => {
    if (!query.trim()) return;
    setHuntLoading(true);
    setHuntError('');
    const t0 = Date.now();
    try {
      const res = await fetch(`${API}/api/advanced-hunting/run`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ query, time_range_hours: parseInt(timeRange), limit: parseInt(limit) }),
      });
      const data = await res.json();
      const rows: HuntResult[] = Array.isArray(data.results) ? data.results : [];
      setResults(rows);
      setHuntStats({ count: rows.length, ms: data.elapsed_ms ?? Date.now() - t0 });
    } catch {
      setHuntError('Failed to run hunt query.');
    } finally {
      setHuntLoading(false);
    }
  };

  const loadSavedQueries = async () => {
    setSqLoading(true);
    try {
      const res = await fetch(`${API}/api/advanced-hunting/queries`, { headers: authHeaders() });
      const data = await res.json();
      setSavedQueries(Array.isArray(data) ? data : data.queries ?? []);
    } catch { /* ignore */ }
    finally { setSqLoading(false); }
  };

  const saveQuery = async () => {
    if (!saveName.trim()) return;
    await fetch(`${API}/api/advanced-hunting/queries`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ name: saveName, description: saveDesc, query }),
    });
    setShowSaveModal(false);
    setSaveName('');
    setSaveDesc('');
    if (activeTab === 'saved') loadSavedQueries();
  };

  const deleteQuery = async (id: string) => {
    await fetch(`${API}/api/advanced-hunting/queries/${id}`, { method: 'DELETE', headers: authHeaders() });
    setSavedQueries(q => q.filter(x => x.id !== id));
  };

  const searchIoc = async () => {
    if (!iocValue.trim()) return;
    setIocLoading(true);
    try {
      const res = await fetch(`${API}/api/advanced-hunting/ioc-search?indicator=${encodeURIComponent(iocValue)}&ioc_type=${iocType}`, { headers: authHeaders() });
      const data = await res.json();
      setIocResult(data);
    } catch { /* ignore */ }
    finally { setIocLoading(false); }
  };

  const loadTemplates = async () => {
    setTplLoading(true);
    try {
      const res = await fetch(`${API}/api/advanced-hunting/templates`, { headers: authHeaders() });
      const data = await res.json();
      setTemplates(Array.isArray(data) ? data : data.templates ?? []);
    } catch { /* ignore */ }
    finally { setTplLoading(false); }
  };

  const resultColumns = results.length > 0 ? Object.keys(results[0]).slice(0, 6) : [];

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'hunt', label: 'Hunt', icon: <Play size={14} /> },
    { id: 'saved', label: 'Saved Queries', icon: <Save size={14} /> },
    { id: 'ioc', label: 'IOC Search', icon: <Search size={14} /> },
    { id: 'templates', label: 'Templates', icon: <Code size={14} /> },
  ];

  return (
    <div className="min-h-screen bg-slate-900 text-white p-6">
      <div className="flex items-center gap-3 mb-6">
        <Shield size={24} className="text-blue-400" />
        <h1 className="text-2xl font-bold">Advanced Threat Hunting</h1>
      </div>

      <div className="flex gap-1 mb-6 border-b border-slate-700">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-t transition-colors ${
              activeTab === t.id ? 'bg-slate-800 text-blue-400 border-b-2 border-blue-400' : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
          >
            {t.icon}{t.label}
          </button>
        ))}
      </div>

      {activeTab === 'hunt' && (
        <div className="space-y-4">
          <div className="bg-slate-800 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <Code size={16} className="text-blue-400" />
              <span className="text-sm font-medium text-slate-300">KQL Query Editor</span>
            </div>
            <textarea
              ref={textareaRef}
              value={query}
              onChange={e => setQuery(e.target.value)}
              className="w-full h-40 bg-slate-900 text-green-400 font-mono text-sm p-3 rounded border border-slate-700 focus:border-blue-500 focus:outline-none resize-y"
              placeholder="SecurityEvent | where EventID == 4625 | where TimeGenerated > ago(1h)"
              spellCheck={false}
            />
            <div className="flex flex-wrap gap-3 mt-3 items-center justify-between">
              <div className="flex gap-3">
                <div className="flex items-center gap-2">
                  <Clock size={14} className="text-slate-400" />
                  <select value={timeRange} onChange={e => setTimeRange(e.target.value)}
                    className="bg-slate-700 text-white text-sm rounded px-2 py-1 border border-slate-600">
                    <option value="1">Last 1h</option>
                    <option value="6">Last 6h</option>
                    <option value="24">Last 24h</option>
                    <option value="168">Last 7d</option>
                    <option value="720">Last 30d</option>
                  </select>
                </div>
                <div className="flex items-center gap-2">
                  <Database size={14} className="text-slate-400" />
                  <select value={limit} onChange={e => setLimit(e.target.value)}
                    className="bg-slate-700 text-white text-sm rounded px-2 py-1 border border-slate-600">
                    <option value="100">100 results</option>
                    <option value="500">500 results</option>
                    <option value="1000">1000 results</option>
                  </select>
                </div>
              </div>
              <div className="flex gap-2">
                <button onClick={() => setShowSaveModal(true)} disabled={!query.trim()}
                  className="flex items-center gap-2 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-sm rounded transition-colors disabled:opacity-40">
                  <Save size={14} /> Save Query
                </button>
                <button onClick={runHunt} disabled={huntLoading || !query.trim()}
                  className="flex items-center gap-2 px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-sm rounded transition-colors disabled:opacity-50">
                  <Play size={14} /> {huntLoading ? 'Running...' : 'Run Hunt'}
                </button>
              </div>
            </div>
          </div>

          {huntError && <div className="bg-red-900/40 border border-red-700 text-red-300 px-4 py-2 rounded text-sm">{huntError}</div>}

          {huntStats && (
            <div className="flex items-center gap-4 text-sm text-slate-400">
              <span className="text-green-400 font-medium">{huntStats.count} results</span>
              <span>in {huntStats.ms}ms</span>
            </div>
          )}

          {results.length > 0 && (
            <div className="bg-slate-800 rounded-lg overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-700">
                      {resultColumns.map(col => (
                        <th key={col} className="text-left px-3 py-2 text-slate-300 font-medium whitespace-nowrap">{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {results.slice(0, 200).map((row, i) => (
                      <tr key={i} className="border-t border-slate-700 hover:bg-slate-700/50">
                        {resultColumns.map(col => (
                          <td key={col} className="px-3 py-2 text-slate-300 truncate max-w-xs" title={String(row[col] ?? '')}>
                            {String(row[col] ?? '')}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'saved' && (
        <div>
          {sqLoading ? (
            <div className="text-slate-400 text-sm">Loading saved queries...</div>
          ) : savedQueries.length === 0 ? (
            <div className="text-slate-400 text-sm text-center py-12">No saved queries yet. Run a hunt and save your query.</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {savedQueries.map(q => (
                <div key={q.id} className="bg-slate-800 rounded-lg p-4 flex flex-col gap-2">
                  <div className="flex items-start justify-between">
                    <h3 className="font-medium text-white text-sm">{q.name}</h3>
                    <span className="text-xs bg-blue-900/50 text-blue-300 px-2 py-0.5 rounded">{q.category || 'Custom'}</span>
                  </div>
                  <p className="text-slate-400 text-xs line-clamp-2">{q.description}</p>
                  <div className="flex gap-2 text-xs text-slate-500 mt-1">
                    <Clock size={11} />
                    <span>{q.last_run ? new Date(q.last_run).toLocaleDateString() : 'Never'}</span>
                    <span>•</span>
                    <span>{q.run_count ?? 0} runs</span>
                  </div>
                  <div className="flex gap-2 mt-2">
                    <button onClick={() => { setQuery(q.query); setActiveTab('hunt'); }}
                      className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 bg-blue-700 hover:bg-blue-600 text-xs rounded transition-colors">
                      <Play size={12} /> Run
                    </button>
                    <button onClick={() => deleteQuery(q.id)}
                      className="px-2 py-1.5 bg-red-900/50 hover:bg-red-800 text-xs rounded transition-colors text-red-300">
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'ioc' && (
        <div className="space-y-4">
          <div className="bg-slate-800 rounded-lg p-4">
            <div className="flex gap-3">
              <input value={iocValue} onChange={e => setIocValue(e.target.value)}
                className="flex-1 bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none"
                placeholder="Enter IP, domain, hash, URL, or email..." />
              <select value={iocType} onChange={e => setIocType(e.target.value)}
                className="bg-slate-700 text-white text-sm rounded px-2 py-2 border border-slate-600">
                {['IP', 'Domain', 'URL', 'Hash', 'Email'].map(t => <option key={t}>{t}</option>)}
              </select>
              <button onClick={searchIoc} disabled={iocLoading || !iocValue.trim()}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-sm rounded transition-colors disabled:opacity-50">
                <Search size={14} /> {iocLoading ? 'Searching...' : 'Search'}
              </button>
            </div>
          </div>
          {iocResult && (
            <div className="bg-slate-800 rounded-lg p-4 space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-sm text-slate-300">Matches found:</span>
                <span className="bg-orange-900/50 text-orange-300 text-xs px-2 py-0.5 rounded font-medium">{iocResult.match_count ?? iocResult.matches?.length ?? 0}</span>
              </div>
              {iocResult.matches?.length > 0 ? (
                <div className="space-y-2">
                  {iocResult.matches.map((m, i) => (
                    <div key={i} className="bg-slate-900 rounded p-3 text-sm">
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-blue-400 font-medium">{m.source}</span>
                        <span className="text-slate-500 text-xs">{m.timestamp ? new Date(m.timestamp).toLocaleString() : ''}</span>
                      </div>
                      <p className="text-slate-300 text-xs">{m.details}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-slate-400 text-sm">No matches found for this indicator.</p>
              )}
            </div>
          )}
        </div>
      )}

      {activeTab === 'templates' && (
        <div>
          {tplLoading ? (
            <div className="text-slate-400 text-sm">Loading templates...</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {templates.map(t => (
                <div key={t.id} className="bg-slate-800 rounded-lg p-4 flex flex-col gap-2">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-medium text-white text-sm">{t.name}</h3>
                    <span className="text-xs bg-purple-900/50 text-purple-300 px-2 py-0.5 rounded whitespace-nowrap">{t.mitre_technique}</span>
                  </div>
                  <p className="text-slate-400 text-xs flex-1">{t.description}</p>
                  <button onClick={() => { setQuery(t.query); setActiveTab('hunt'); }}
                    className="mt-2 flex items-center justify-center gap-1 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-xs rounded transition-colors">
                    <Code size={12} /> Load Template
                  </button>
                </div>
              ))}
              {templates.length === 0 && (
                <div className="col-span-3 text-center text-slate-400 text-sm py-12">No templates available.</div>
              )}
            </div>
          )}
        </div>
      )}

      {showSaveModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-xl p-6 w-full max-w-md border border-slate-700">
            <h2 className="text-lg font-semibold mb-4">Save Query</h2>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">Name *</label>
                <input value={saveName} onChange={e => setSaveName(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  placeholder="Query name" />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Description</label>
                <textarea value={saveDesc} onChange={e => setSaveDesc(e.target.value)}
                  className="w-full h-20 bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none resize-none"
                  placeholder="Describe what this query detects..." />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <button onClick={() => setShowSaveModal(false)}
                className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-sm rounded transition-colors">Cancel</button>
              <button onClick={saveQuery} disabled={!saveName.trim()}
                className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-sm rounded transition-colors disabled:opacity-50">
                <Save size={14} className="inline mr-1" /> Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
