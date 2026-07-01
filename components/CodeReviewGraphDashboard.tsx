import React, { useState, useCallback } from 'react';
import { AlertTriangle, CheckCircle, Search, RefreshCw, GitBranch, Code2, Layers, Activity } from 'lucide-react';

const API = '/api/code-review';

interface GraphStats {
  total_nodes: number;
  total_edges: number;
  files_count: number;
  languages: string[];
  last_updated: string | null;
  summary?: string;
}

interface AnalysisResult {
  risk_score?: number;
  changed_functions?: string[];
  impacted_nodes?: string[];
  untested_functions?: string[];
  summary?: string;
  error?: string;
}

interface SearchResult {
  nodes?: Array<{ name: string; kind: string; file_path: string; line_start?: number }>;
  summary?: string;
}

const RiskBadge: React.FC<{ score: number }> = ({ score }) => {
  const pct = Math.round(score * 100);
  const color = pct >= 70 ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
    : pct >= 40 ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
    : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400';
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-semibold ${color}`}>
      <AlertTriangle size={12} /> Risk {pct}%
    </span>
  );
};

const StatCard: React.FC<{ label: string; value: string | number; icon: React.ReactNode }> = ({ label, value, icon }) => (
  <div className="bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-200 dark:border-gray-700 flex items-center gap-3">
    <div className="text-primary-500">{icon}</div>
    <div>
      <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      <p className="text-xl font-bold text-gray-900 dark:text-white">{value}</p>
    </div>
  </div>
);

export const CodeReviewGraphDashboard: React.FC = () => {
  const [repoRoot, setRepoRoot] = useState('');
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult | null>(null);
  const [changedFiles, setChangedFiles] = useState('');
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const call = useCallback(async (fn: () => Promise<Response>) => {
    setError(null);
    try {
      const res = await fn();
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(body.detail || res.statusText);
      }
      return await res.json();
    } catch (e: any) {
      setError(e.message || 'Request failed');
      return null;
    }
  }, []);

  const loadStats = async () => {
    if (!repoRoot.trim()) return setError('Enter a repository path first.');
    setLoading('stats');
    const data = await call(() => fetch(`${API}/graph/stats?repo_root=${encodeURIComponent(repoRoot)}`));
    if (data) setStats(data);
    setLoading(null);
  };

  const buildGraph = async (full: boolean) => {
    if (!repoRoot.trim()) return setError('Enter a repository path first.');
    setLoading('build');
    const data = await call(() => fetch(`${API}/graph/build`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_root: repoRoot, full_rebuild: full }),
    }));
    if (data) { setStats(null); await loadStats(); }
    setLoading(null);
  };

  const analyzeChanges = async () => {
    if (!repoRoot.trim()) return setError('Enter a repository path first.');
    setLoading('analyze');
    const files = changedFiles.trim() ? changedFiles.split('\n').map(f => f.trim()).filter(Boolean) : undefined;
    const data = await call(() => fetch(`${API}/graph/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_root: repoRoot, changed_files: files ?? null }),
    }));
    if (data) setAnalysis(data);
    setLoading(null);
  };

  const search = async () => {
    if (!repoRoot.trim() || !searchQuery.trim()) return setError('Enter both a repository path and a search query.');
    setLoading('search');
    const data = await call(() =>
      fetch(`${API}/graph/search?repo_root=${encodeURIComponent(repoRoot)}&query=${encodeURIComponent(searchQuery)}&limit=20`)
    );
    if (data) setSearchResults(data);
    setLoading(null);
  };

  return (
    <div className="space-y-6 p-1">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <GitBranch size={22} className="text-primary-500" />
            Code Review Graph
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Persistent knowledge graph for impact analysis and code review context
          </p>
        </div>
      </div>

      {/* Repo Path Input */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Repository Root Path</label>
        <div className="flex gap-2">
          <input
            type="text"
            className="flex-1 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-400 outline-none"
            placeholder="/absolute/path/to/your/repo"
            value={repoRoot}
            onChange={e => setRepoRoot(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && loadStats()}
          />
          <button
            onClick={loadStats}
            disabled={loading === 'stats'}
            className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg flex items-center gap-2 disabled:opacity-50"
          >
            <Activity size={14} />
            {loading === 'stats' ? 'Loading…' : 'Load Stats'}
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 text-sm">
          <AlertTriangle size={16} /> {error}
        </div>
      )}

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Nodes" value={stats.total_nodes?.toLocaleString() ?? '—'} icon={<Code2 size={20} />} />
          <StatCard label="Edges" value={stats.total_edges?.toLocaleString() ?? '—'} icon={<GitBranch size={20} />} />
          <StatCard label="Files" value={stats.files_count?.toLocaleString() ?? '—'} icon={<Layers size={20} />} />
          <StatCard
            label="Languages"
            value={stats.languages?.length ? stats.languages.slice(0, 3).join(', ') + (stats.languages.length > 3 ? '…' : '') : '—'}
            icon={<Activity size={20} />}
          />
        </div>
      )}

      {/* Build Controls */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Graph Build</h2>
        <div className="flex gap-2">
          <button
            onClick={() => buildGraph(false)}
            disabled={!!loading}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg flex items-center gap-2 disabled:opacity-50"
          >
            <RefreshCw size={14} className={loading === 'build' ? 'animate-spin' : ''} />
            Incremental Update
          </button>
          <button
            onClick={() => buildGraph(true)}
            disabled={!!loading}
            className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white text-sm font-medium rounded-lg flex items-center gap-2 disabled:opacity-50"
          >
            <RefreshCw size={14} />
            Full Rebuild
          </button>
        </div>
        {stats?.last_updated && (
          <p className="text-xs text-gray-400 mt-2">Last built: {stats.last_updated}</p>
        )}
      </div>

      {/* Change Analysis */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Change Impact Analysis</h2>
        <textarea
          className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-white text-sm font-mono mb-2 focus:ring-2 focus:ring-primary-400 outline-none resize-none"
          rows={3}
          placeholder="Optional: one changed file path per line. Leave blank to auto-detect from git diff."
          value={changedFiles}
          onChange={e => setChangedFiles(e.target.value)}
        />
        <button
          onClick={analyzeChanges}
          disabled={!!loading}
          className="px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white text-sm font-medium rounded-lg flex items-center gap-2 disabled:opacity-50"
        >
          <AlertTriangle size={14} />
          {loading === 'analyze' ? 'Analyzing…' : 'Analyze Changes'}
        </button>

        {analysis && (
          <div className="mt-4 space-y-3">
            {analysis.error ? (
              <p className="text-sm text-red-500">{analysis.error}</p>
            ) : (
              <>
                {analysis.risk_score !== undefined && (
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-600 dark:text-gray-400">Overall risk:</span>
                    <RiskBadge score={analysis.risk_score} />
                  </div>
                )}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                  {analysis.changed_functions && (
                    <div className="p-3 rounded-lg bg-blue-50 dark:bg-blue-900/20">
                      <p className="font-medium text-blue-700 dark:text-blue-400 mb-1">Changed Functions</p>
                      <p className="text-2xl font-bold text-blue-900 dark:text-blue-300">{analysis.changed_functions.length}</p>
                    </div>
                  )}
                  {analysis.impacted_nodes && (
                    <div className="p-3 rounded-lg bg-orange-50 dark:bg-orange-900/20">
                      <p className="font-medium text-orange-700 dark:text-orange-400 mb-1">Impacted Nodes</p>
                      <p className="text-2xl font-bold text-orange-900 dark:text-orange-300">{analysis.impacted_nodes.length}</p>
                    </div>
                  )}
                  {analysis.untested_functions && (
                    <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20">
                      <p className="font-medium text-red-700 dark:text-red-400 mb-1">Untested Functions</p>
                      <p className="text-2xl font-bold text-red-900 dark:text-red-300">{analysis.untested_functions.length}</p>
                    </div>
                  )}
                </div>
                {analysis.summary && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-2 whitespace-pre-wrap">{analysis.summary}</p>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* Code Search */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Code Entity Search</h2>
        <div className="flex gap-2 mb-3">
          <input
            type="text"
            className="flex-1 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-400 outline-none"
            placeholder="Search for functions, classes, files…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && search()}
          />
          <button
            onClick={search}
            disabled={!!loading}
            className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg flex items-center gap-2 disabled:opacity-50"
          >
            <Search size={14} />
            {loading === 'search' ? 'Searching…' : 'Search'}
          </button>
        </div>

        {searchResults?.nodes && searchResults.nodes.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                  <th className="pb-2 pr-4 font-medium">Name</th>
                  <th className="pb-2 pr-4 font-medium">Kind</th>
                  <th className="pb-2 font-medium">File</th>
                </tr>
              </thead>
              <tbody>
                {searchResults.nodes.map((n, i) => (
                  <tr key={i} className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-900/40">
                    <td className="py-1.5 pr-4 font-mono text-primary-600 dark:text-primary-400">{n.name}</td>
                    <td className="py-1.5 pr-4">
                      <span className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">{n.kind}</span>
                    </td>
                    <td className="py-1.5 text-gray-500 dark:text-gray-400 truncate max-w-xs">
                      {n.file_path}{n.line_start ? `:${n.line_start}` : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {searchResults?.nodes?.length === 0 && (
          <div className="flex items-center gap-2 text-sm text-gray-400 mt-2">
            <CheckCircle size={14} /> No results found.
          </div>
        )}
      </div>
    </div>
  );
};
