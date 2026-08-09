import React, { useState, useEffect, useCallback } from 'react';

const API = '/api/sca';

interface Policy {
  id: string;
  name: string;
  version: string;
  platform: string;
  total_checks: number;
}

interface AgentSummary {
  agent_id: string;
  hostname?: string;
  passed: number;
  failed: number;
  error: number;
  not_applicable: number;
  score: number;
}

interface Check {
  id: string;
  agent_id: string;
  policy_id: string;
  check_id: string;
  title: string;
  result: 'passed' | 'failed' | 'error' | 'not_applicable';
  rationale?: string;
  remediation?: string;
  scanned_at: string;
}

interface Stats {
  passed: number;
  failed: number;
  error: number;
  not_applicable: number;
  total: number;
  compliance_score: number;
  agents_scanned: number;
}

const RESULT_STYLE: Record<string, string> = {
  passed: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  failed: 'bg-red-500/20 text-red-400 border-red-500/30',
  error: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  not_applicable: 'bg-slate-700/50 text-slate-400 border-slate-600/30',
};

const MOCK_AGENTS: AgentSummary[] = [
  { agent_id: 'a1', hostname: 'web-server-01', passed: 187, failed: 34, error: 2, not_applicable: 18, score: 83 },
  { agent_id: 'a2', hostname: 'db-server-01', passed: 201, failed: 41, error: 0, not_applicable: 7, score: 80 },
  { agent_id: 'a3', hostname: 'workstation-ceo', passed: 165, failed: 52, error: 5, not_applicable: 19, score: 73 },
  { agent_id: 'a4', hostname: 'dev-laptop-01', passed: 142, failed: 78, error: 3, not_applicable: 18, score: 63 },
];

const MOCK_STATS: Stats = {
  passed: 695, failed: 205, error: 10, not_applicable: 62, total: 972,
  compliance_score: 71.5, agents_scanned: 4,
};

const token = () => sessionStorage.getItem('token') ?? '';
const h = () => ({ Authorization: `Bearer ${token()}` });

export default function SCADashboard() {
  const [tab, setTab] = useState<'overview' | 'agents' | 'policies'>('overview');
  const [stats, setStats] = useState<Stats>(MOCK_STATS);
  const [agents, setAgents] = useState<AgentSummary[]>(MOCK_AGENTS);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<AgentSummary | null>(null);
  const [checks, setChecks] = useState<Check[]>([]);
  const [filterResult, setFilterResult] = useState('');
  const [scanMsg, setScanMsg] = useState('');

  const load = useCallback(async () => {
    try {
      const [s, p] = await Promise.all([
        fetch(`${API}/stats`, { headers: h() }).then(r => r.ok ? r.json() : null),
        fetch(`${API}/policies`, { headers: h() }).then(r => r.ok ? r.json() : null),
      ]);
      if (s) setStats(s);
      if (p) setPolicies(p);
    } catch { /* use mock */ }
  }, []);

  const loadAgentChecks = useCallback(async (agent: AgentSummary) => {
    setSelectedAgent(agent);
    try {
      const url = `${API}/agents/${agent.agent_id}/checks${filterResult ? `?result=${filterResult}` : ''}`;
      const r = await fetch(url, { headers: h() });
      if (r.ok) setChecks(await r.json());
    } catch { setChecks([]); }
  }, [filterResult]);

  const triggerScan = async (agentId: string, policyId: string) => {
    setScanMsg('');
    try {
      const r = await fetch(`${API}/scan/${agentId}`, {
        method: 'POST',
        headers: { ...h(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ policy_id: policyId }),
      });
      const d = await r.json();
      setScanMsg(d.message ?? 'Scan queued');
    } catch { setScanMsg('Failed to queue scan'); }
    setTimeout(() => setScanMsg(''), 4000);
  };

  useEffect(() => { load(); }, [load]);

  const scoreColor = (s: number) =>
    s >= 80 ? 'text-emerald-400' : s >= 60 ? 'text-yellow-400' : 'text-red-400';

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Security Configuration Assessment</h2>
        <span className="text-sm text-slate-400">{stats.agents_scanned} agents scanned</span>
      </div>

      {scanMsg && (
        <div className="bg-blue-500/20 border border-blue-500/30 text-blue-300 text-sm px-4 py-2 rounded-lg">{scanMsg}</div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: 'Compliance Score', value: `${stats.compliance_score}%`, cls: scoreColor(stats.compliance_score) },
          { label: 'Passed', value: stats.passed, cls: 'text-emerald-400' },
          { label: 'Failed', value: stats.failed, cls: 'text-red-400' },
          { label: 'Errors', value: stats.error, cls: 'text-yellow-400' },
          { label: 'N/A', value: stats.not_applicable, cls: 'text-slate-400' },
        ].map(k => (
          <div key={k.label} className="bg-slate-800 border border-slate-700 rounded-xl p-4 text-center">
            <div className={`text-2xl font-bold ${k.cls}`}>{k.value}</div>
            <div className="text-xs text-slate-400 mt-1">{k.label}</div>
          </div>
        ))}
      </div>

      <div className="flex rounded-lg overflow-hidden border border-slate-700 w-fit">
        {(['overview', 'agents', 'policies'] as const).map(t => (
          <button key={t} onClick={() => { setTab(t); setSelectedAgent(null); }}
            className={`px-4 py-2 text-sm font-medium capitalize transition-colors ${tab === t ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>
            {t === 'overview' ? 'Overview' : t === 'agents' ? 'By Agent' : 'Policies'}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
          <div className="p-4 border-b border-slate-700">
            <h3 className="text-sm font-semibold text-white">Agent Compliance Summary</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-slate-400 text-xs">
                  <th className="px-4 py-2 text-left">Hostname</th>
                  <th className="px-4 py-2 text-right">Score</th>
                  <th className="px-4 py-2 text-right">Passed</th>
                  <th className="px-4 py-2 text-right">Failed</th>
                  <th className="px-4 py-2 text-right">Errors</th>
                  <th className="px-4 py-2 text-right">N/A</th>
                </tr>
              </thead>
              <tbody>
                {agents.map(a => (
                  <tr key={a.agent_id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                    <td className="px-4 py-3 text-slate-200 font-mono text-xs">{a.hostname ?? a.agent_id}</td>
                    <td className={`px-4 py-3 text-right font-bold ${scoreColor(a.score)}`}>{a.score}%</td>
                    <td className="px-4 py-3 text-right text-emerald-400">{a.passed}</td>
                    <td className="px-4 py-3 text-right text-red-400">{a.failed}</td>
                    <td className="px-4 py-3 text-right text-yellow-400">{a.error}</td>
                    <td className="px-4 py-3 text-right text-slate-400">{a.not_applicable}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'agents' && !selectedAgent && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {agents.map(a => (
            <div key={a.agent_id} className="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3 cursor-pointer hover:border-blue-500/50 transition-colors"
              onClick={() => loadAgentChecks(a)}>
              <div className="flex items-center justify-between">
                <span className="font-semibold text-white">{a.hostname ?? a.agent_id}</span>
                <span className={`text-lg font-bold ${scoreColor(a.score)}`}>{a.score}%</span>
              </div>
              <div className="flex gap-3 text-xs">
                <span className="text-emerald-400">{a.passed} passed</span>
                <span className="text-red-400">{a.failed} failed</span>
                <span className="text-yellow-400">{a.error} errors</span>
              </div>
              <div className="w-full bg-slate-700 rounded-full h-1.5">
                <div className="bg-emerald-500 h-1.5 rounded-full" style={{ width: `${a.score}%` }} />
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === 'agents' && selectedAgent && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <button onClick={() => setSelectedAgent(null)} className="text-slate-400 hover:text-white text-sm">← Back</button>
            <h3 className="text-white font-semibold">{selectedAgent.hostname}</h3>
            <select value={filterResult} onChange={e => setFilterResult(e.target.value)}
              className="ml-auto bg-slate-800 border border-slate-700 text-slate-300 text-xs rounded px-2 py-1">
              <option value="">All Results</option>
              <option value="failed">Failed</option>
              <option value="passed">Passed</option>
              <option value="error">Error</option>
            </select>
          </div>
          {checks.length === 0 ? (
            <div className="text-slate-400 text-sm text-center py-12">No checks loaded — click agent to fetch from backend.</div>
          ) : (
            <div className="space-y-2">
              {checks.map((c, i) => (
                <div key={i} className="bg-slate-800 border border-slate-700 rounded-lg p-3 flex items-start gap-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full border capitalize shrink-0 ${RESULT_STYLE[c.result]}`}>{c.result}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-slate-200 text-sm">{c.title}</div>
                    {c.remediation && <div className="text-slate-400 text-xs mt-1">{c.remediation}</div>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'policies' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {(policies.length > 0 ? policies : []).map(p => (
            <div key={p.id} className="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3">
              <div>
                <div className="font-semibold text-white text-sm">{p.name}</div>
                <div className="text-xs text-slate-400 mt-0.5">v{p.version} · {p.total_checks} checks</div>
              </div>
              <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-400 border border-blue-500/30 capitalize">{p.platform}</span>
              <button onClick={() => triggerScan(agents[0]?.agent_id ?? '', p.id)}
                className="w-full py-1.5 text-xs rounded-lg bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors">
                Trigger Scan
              </button>
            </div>
          ))}
          {policies.length === 0 && (
            <div className="col-span-3 text-center text-slate-400 text-sm py-12">Loading policies…</div>
          )}
        </div>
      )}
    </div>
  );
}
