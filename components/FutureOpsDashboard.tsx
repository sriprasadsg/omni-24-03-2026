import React, { useEffect, useState } from 'react';
import { Cpu, Activity, Globe, Zap } from 'lucide-react';
import { getJobs, fetchAgents } from '../services/apiService';

const ACTIVE_STATUSES = new Set(['pending', 'queued', 'running', 'in_progress']);
const DONE_STATUSES = new Set(['completed', 'success', 'succeeded', 'failed']);

// Operations summary from the job queue and agent fleet (replaces a static mock-up)
export const opsSummary = (jobs: any[], agents: any[], now = Date.now()) => {
    const status = (j: any) => String(j.status || '').toLowerCase();
    const finishedAt = (j: any) => Date.parse(j.completed_at || j.updated_at || j.created_at || '');
    const online = agents.filter(a => String(a.status || '').toLowerCase() === 'online').length;
    return {
        active: jobs.filter(j => ACTIVE_STATUSES.has(status(j))).length,
        finished24h: jobs.filter(j => DONE_STATUSES.has(status(j)) && now - finishedAt(j) <= 86_400_000).length,
        endpoints: agents.length,
        onlinePct: agents.length ? Math.round((online / agents.length) * 100) : null,
    };
};

const FutureOpsDashboard: React.FC = () => {
  const [jobs, setJobs] = useState<any[]>([]);
  const [agents, setAgents] = useState<any[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const load = async () => {
      const [j, a] = await Promise.all([getJobs(), fetchAgents()]);
      setJobs(Array.isArray(j) ? j : []);
      setAgents(Array.isArray(a) ? a : []);
      setLoaded(true);
    };
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []);

  const s = opsSummary(jobs, agents);
  const stats = [
    { label: 'Active Jobs', value: loaded ? String(s.active) : '…', icon: Activity, color: 'text-emerald-600 dark:text-emerald-400' },
    { label: 'Jobs Finished (24h)', value: loaded ? String(s.finished24h) : '…', icon: Zap, color: 'text-amber-700 dark:text-amber-400' },
    { label: 'Managed Endpoints', value: loaded ? String(s.endpoints) : '…', icon: Globe, color: 'text-indigo-600 dark:text-indigo-400' },
    { label: 'Agents Online', value: loaded ? (s.onlinePct === null ? '—' : `${s.onlinePct}%`) : '…', icon: Cpu, color: 'text-cyan-600 dark:text-cyan-400' },
  ];

  return (
    <div className="p-8 bg-transparent dark:bg-[#040812] min-h-screen text-gray-900 dark:text-slate-100 font-sans">
      <div className="max-w-7xl mx-auto">
        <div className="mb-10">
          <h1 className="text-4xl font-black tracking-tight mb-2 bg-gradient-to-r from-cyan-400 to-indigo-500 bg-clip-text text-transparent">
            UNIFIED OPERATIONS
          </h1>
          <p className="text-gray-600 dark:text-slate-400 text-lg">Job queue and endpoint fleet at a glance</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          {stats.map((stat) => (
            <div key={stat.label} className="bg-white/50 dark:bg-slate-900/50 border border-gray-200 dark:border-slate-800 p-6 rounded-2xl backdrop-blur-sm">
              <div className="flex justify-between items-start mb-4">
                <div className={`p-2 rounded-lg bg-white dark:bg-slate-800 ${stat.color}`}>
                  <stat.icon size={20} />
                </div>
              </div>
              <p className="text-slate-500 text-sm font-medium mb-1">{stat.label}</p>
              <h3 className="text-3xl font-bold">{stat.value}</h3>
            </div>
          ))}
        </div>

        <div className="bg-white/50 dark:bg-slate-900/50 border border-gray-200 dark:border-slate-800 rounded-2xl p-6">
          <h2 className="text-lg font-bold mb-4">Recent Jobs</h2>
          {loaded && jobs.length === 0 ? (
            <p className="text-slate-500 text-sm">No jobs have run yet.</p>
          ) : (
            <ul className="divide-y divide-gray-200 dark:divide-slate-800">
              {jobs.slice(0, 8).map((j, i) => (
                <li key={j.id || i} className="py-2 flex justify-between text-sm">
                  <span className="text-gray-700 dark:text-slate-300">{j.type || 'job'}</span>
                  <span className="text-slate-500">{j.status}{j.created_at ? ` · ${new Date(j.created_at).toLocaleString()}` : ''}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
};

export default FutureOpsDashboard;
