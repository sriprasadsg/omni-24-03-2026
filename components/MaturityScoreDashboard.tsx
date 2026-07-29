import React, { useState, useEffect, useCallback } from 'react';
import { TrendingUp, Target, AlertTriangle, Plus, Save, BarChart2 } from 'lucide-react';

interface Assessment {
  id: string;
  domain: string;
  framework: string;
  level: number;
  levelName: string;
  evidence: string;
  notes: string;
  targetLevel?: number;
  assessed_by: string;
  assessed_at: string;
}

interface Summary {
  averageLevel: number;
  levelName: string;
  byDomain: Record<string, number>;
  byLevel: Record<string, number>;
  totalDomains: number;
  assessedDomains: number;
  coveragePct: number;
}

interface Gap { domain: string; currentLevel: number; targetLevel: number; gap: number; status: string; }

const LEVEL_COLORS = ['', 'bg-red-500', 'bg-orange-500', 'bg-yellow-500', 'bg-blue-500', 'bg-green-500'];
const LEVEL_LABELS = ['', 'Initial', 'Managed', 'Defined', 'Quantitatively Managed', 'Optimizing'];
const authHeader = () => ({ Authorization: `Bearer ${sessionStorage.getItem('token')}`, 'Content-Type': 'application/json' });

function LevelBar({ level, target }: { level: number; target?: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex gap-0.5">
        {[1, 2, 3, 4, 5].map(l => (
          <div key={l} className={`w-5 h-3 rounded-sm ${l <= level ? LEVEL_COLORS[level] : 'bg-gray-200 dark:bg-gray-700'}`} />
        ))}
      </div>
      <span className="text-xs text-gray-500 dark:text-gray-400">L{level}</span>
      {target && target > level && <span className="text-xs text-orange-500">→ L{target}</span>}
    </div>
  );
}

export default function MaturityScoreDashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [gaps, setGaps] = useState<Gap[]>([]);
  const [domains, setDomains] = useState<string[]>([]);
  const [framework, setFramework] = useState('General');
  const [loading, setLoading] = useState(true);
  const [editingDomain, setEditingDomain] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ level: 1, targetLevel: 3, evidence: '', notes: '' });
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<'overview' | 'gaps' | 'domains'>('overview');

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const params = framework ? `?framework=${encodeURIComponent(framework)}` : '';
      const [sumRes, assRes, gapRes, domRes] = await Promise.all([
        fetch(`/api/maturity/summary${params}`, { headers: authHeader() }),
        fetch(`/api/maturity${params}`, { headers: authHeader() }),
        fetch(`/api/maturity/gaps${params}`, { headers: authHeader() }),
        fetch('/api/maturity/domains', { headers: authHeader() }),
      ]);
      if (sumRes.ok) setSummary(await sumRes.json());
      if (assRes.ok) setAssessments(await assRes.json());
      if (gapRes.ok) setGaps(await gapRes.json());
      if (domRes.ok) { const d = await domRes.json(); setDomains(d.domains || []); }
    } finally { setLoading(false); }
  }, [framework]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const assessedMap = Object.fromEntries(assessments.map(a => [a.domain, a]));

  const startEdit = (domain: string) => {
    const existing = assessedMap[domain];
    setEditForm({ level: existing?.level || 1, targetLevel: existing?.targetLevel || 3, evidence: existing?.evidence || '', notes: existing?.notes || '' });
    setEditingDomain(domain);
  };

  const saveAssessment = async () => {
    if (!editingDomain) return;
    setSaving(true);
    try {
      await fetch('/api/maturity', {
        method: 'POST',
        headers: authHeader(),
        body: JSON.stringify({ domain: editingDomain, framework, ...editForm }),
      });
      setEditingDomain(null);
      await fetchAll();
    } finally { setSaving(false); }
  };

  const frameworks = ['General', 'ISO 27001', 'SOC 2', 'NIST 800-53', 'CIS Controls', 'CMMC'];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-primary-500" /> Maturity Assessment
        </h2>
        <select value={framework} onChange={e => setFramework(e.target.value)} className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg">
          {frameworks.map(f => <option key={f}>{f}</option>)}
        </select>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 col-span-2 md:col-span-1">
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Average Maturity Level</p>
            <p className="text-4xl font-bold text-primary-600 dark:text-primary-400">{summary.averageLevel}</p>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{summary.levelName}</p>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Domains Assessed</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">{summary.assessedDomains}<span className="text-gray-400 text-base">/{summary.totalDomains}</span></p>
            <div className="mt-2 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div className="h-full bg-primary-500 rounded-full" style={{ width: `${summary.coveragePct}%` }} />
            </div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">By Level</p>
            {Object.entries(summary.byLevel).map(([name, count]) => (
              <div key={name} className="flex justify-between text-xs mb-1">
                <span className="text-gray-600 dark:text-gray-400 truncate">{name}</span>
                <span className="font-medium text-gray-900 dark:text-white ml-2">{count}</span>
              </div>
            ))}
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Gaps to Close</p>
            <p className="text-2xl font-bold text-orange-500">{gaps.length}</p>
            <p className="text-xs text-gray-400 mt-1">domains below target</p>
          </div>
        </div>
      )}

      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
        {(['overview', 'gaps', 'domains'] as const).map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)} className={`px-4 py-2 text-sm font-medium capitalize border-b-2 -mb-px transition-colors ${activeTab === tab ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}`}>{tab}</button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" /></div>
      ) : activeTab === 'gaps' ? (
        <div className="space-y-2">
          {gaps.length === 0 ? <p className="text-center py-8 text-gray-400 dark:text-gray-500">No gaps — all assessed domains meet their targets.</p> : gaps.map(g => (
            <div key={g.domain} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 flex items-center justify-between">
              <div>
                <p className="font-medium text-gray-900 dark:text-white text-sm">{g.domain}</p>
                <p className="text-xs text-gray-400 mt-0.5">{g.status}</p>
              </div>
              <div className="flex items-center gap-3">
                <LevelBar level={g.currentLevel} target={g.targetLevel} />
                <span className="text-xs px-2 py-0.5 bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400 rounded-full">Gap: {g.gap}</span>
                <button onClick={() => startEdit(g.domain)} className="text-xs text-primary-600 hover:text-primary-700 dark:text-primary-400 font-medium">Assess</button>
              </div>
            </div>
          ))}
        </div>
      ) : activeTab === 'domains' ? (
        <div className="grid gap-3">
          {domains.map(domain => {
            const a = assessedMap[domain];
            return (
              <div key={domain} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 flex items-center justify-between">
                <div className="flex-1">
                  <p className="font-medium text-gray-900 dark:text-white text-sm">{domain}</p>
                  {a && <p className="text-xs text-gray-400 mt-0.5">Assessed by {a.assessed_by}</p>}
                </div>
                <div className="flex items-center gap-4">
                  {a ? <LevelBar level={a.level} target={a.targetLevel} /> : <span className="text-xs text-gray-400 italic">Not assessed</span>}
                  <button onClick={() => startEdit(domain)} className="text-xs text-primary-600 hover:text-primary-700 dark:text-primary-400 font-medium">{a ? 'Update' : 'Assess'}</button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="grid gap-3">
          {assessments.map(a => (
            <div key={a.id} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 flex items-center justify-between">
              <div>
                <p className="font-medium text-gray-900 dark:text-white text-sm">{a.domain}</p>
                <p className="text-xs text-gray-400 mt-0.5">{a.framework} · {new Date(a.assessed_at).toLocaleDateString()}</p>
              </div>
              <LevelBar level={a.level} target={a.targetLevel} />
            </div>
          ))}
        </div>
      )}

      {editingDomain && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-md p-6 space-y-4">
            <h3 className="font-semibold text-gray-900 dark:text-white">Assess: {editingDomain}</h3>
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">Current Level (1–5)</label>
              <div className="flex gap-2">
                {[1, 2, 3, 4, 5].map(l => (
                  <button key={l} onClick={() => setEditForm(f => ({ ...f, level: l }))} className={`w-10 h-10 rounded-lg font-medium text-sm ${editForm.level === l ? 'bg-primary-600 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'}`}>{l}</button>
                ))}
              </div>
              <p className="text-xs text-gray-400 mt-1">{LEVEL_LABELS[editForm.level]}</p>
            </div>
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">Target Level</label>
              <div className="flex gap-2">
                {[1, 2, 3, 4, 5].map(l => (
                  <button key={l} onClick={() => setEditForm(f => ({ ...f, targetLevel: l }))} className={`w-10 h-10 rounded-lg font-medium text-sm ${editForm.targetLevel === l ? 'bg-orange-500 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'}`}>{l}</button>
                ))}
              </div>
            </div>
            <textarea value={editForm.evidence} onChange={e => setEditForm(f => ({ ...f, evidence: e.target.value }))} placeholder="Evidence / justification" rows={2} className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg" />
            <textarea value={editForm.notes} onChange={e => setEditForm(f => ({ ...f, notes: e.target.value }))} placeholder="Notes" rows={2} className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg" />
            <div className="flex justify-end gap-2">
              <button onClick={() => setEditingDomain(null)} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900">Cancel</button>
              <button onClick={saveAssessment} disabled={saving} className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50">
                <Save className="w-4 h-4" />{saving ? 'Saving…' : 'Save Assessment'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
