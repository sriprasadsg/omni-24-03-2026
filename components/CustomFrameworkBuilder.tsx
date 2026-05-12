import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';

interface Control {
  id: string;
  name: string;
  description: string;
  evidence_sources: string[];
  severity: string;
  automated: boolean;
  status: string;
  guidance?: string;
}

interface Domain {
  id: string;
  name: string;
  description?: string;
  controls: Control[];
}

interface Framework {
  id: string;
  name: string;
  description: string;
  version: string;
  status: string;
  domains: Domain[];
  control_count: number;
  passing_controls: number;
  compliance_score: number;
  created_at: string;
  tags: string[];
}

interface Template {
  id: string;
  name: string;
  description: string;
}

const EVIDENCE_SOURCES = [
  'log_shipper', 'compliance_evidence_collector', 'network_discovery',
  'process_monitor', 'software_management', 'backup_verifier',
  'vendor_risk', 'real_fim', 'runtime_security',
];

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'text-red-400',
  high: 'text-orange-400',
  medium: 'text-yellow-400',
  low: 'text-green-400',
};

export default function CustomFrameworkBuilder() {
  const [frameworks, setFrameworks] = useState<Framework[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selected, setSelected] = useState<Framework | null>(null);
  const [view, setView] = useState<'list' | 'builder' | 'create'>('list');
  const [evaluation, setEvaluation] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  // Create form state
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newTemplate, setNewTemplate] = useState('blank');

  // Domain / control add state
  const [addingDomain, setAddingDomain] = useState(false);
  const [domainName, setDomainName] = useState('');
  const [addingControl, setAddingControl] = useState<string | null>(null);
  const [controlForm, setControlForm] = useState({ name: '', description: '', severity: 'medium', evidence_sources: [] as string[] });

  useEffect(() => {
    loadFrameworks();
    loadTemplates();
  }, []);

  async function loadFrameworks() {
    try {
      const r = await authFetch('/api/custom-frameworks');
      const d = await r.json();
      setFrameworks(d.frameworks || []);
    } catch (e) {
      console.error('Failed to load frameworks', e);
    }
  }

  async function loadTemplates() {
    try {
      const r = await authFetch('/api/custom-frameworks/templates');
      const d = await r.json();
      setTemplates(d.templates || []);
    } catch (e) {}
  }

  async function createFramework() {
    if (!newName.trim()) return;
    setLoading(true);
    try {
      const r = await authFetch('/api/custom-frameworks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName, description: newDesc, template_id: newTemplate }),
      });
      const d = await r.json();
      setFrameworks(prev => [d.framework, ...prev]);
      setSelected(d.framework);
      setView('builder');
      setNewName(''); setNewDesc('');
    } finally {
      setLoading(false);
    }
  }

  async function addDomain() {
    if (!selected || !domainName.trim()) return;
    const r = await authFetch(`/api/custom-frameworks/${selected.id}/domains`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: domainName }),
    });
    const d = await r.json();
    setSelected(prev => prev ? {
      ...prev,
      domains: [...prev.domains, { ...d.domain, controls: [] }],
    } : prev);
    setDomainName('');
    setAddingDomain(false);
  }

  async function addControl(domainId: string) {
    if (!selected || !controlForm.name.trim()) return;
    const r = await authFetch(`/api/custom-frameworks/${selected.id}/domains/${domainId}/controls`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(controlForm),
    });
    const d = await r.json();
    setSelected(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        domains: prev.domains.map(dom =>
          dom.id === domainId ? { ...dom, controls: [...dom.controls, d.control] } : dom
        ),
      };
    });
    setControlForm({ name: '', description: '', severity: 'medium', evidence_sources: [] });
    setAddingControl(null);
  }

  async function publishFramework() {
    if (!selected) return;
    await authFetch(`/api/custom-frameworks/${selected.id}/publish`, { method: 'POST' });
    setSelected(prev => prev ? { ...prev, status: 'published' } : prev);
    loadFrameworks();
  }

  async function evaluateFramework() {
    if (!selected) return;
    setLoading(true);
    try {
      const r = await authFetch(`/api/custom-frameworks/${selected.id}/evaluate`, { method: 'POST' });
      const d = await r.json();
      setEvaluation(d);
    } finally {
      setLoading(false);
    }
  }

  async function deleteFramework(id: string) {
    await authFetch(`/api/custom-frameworks/${id}`, { method: 'DELETE' });
    setFrameworks(prev => prev.filter(f => f.id !== id));
    if (selected?.id === id) { setSelected(null); setView('list'); }
  }

  function toggleEvidenceSource(src: string) {
    setControlForm(prev => ({
      ...prev,
      evidence_sources: prev.evidence_sources.includes(src)
        ? prev.evidence_sources.filter(s => s !== src)
        : [...prev.evidence_sources, src],
    }));
  }

  const scoreColor = (s: number) => s >= 80 ? 'text-green-400' : s >= 60 ? 'text-yellow-400' : 'text-red-400';

  // ── List View ──────────────────────────────────────────────────────────────
  if (view === 'list') {
    return (
      <div className="p-6 bg-gray-900 min-h-screen text-white">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-2xl font-bold">Custom Compliance Frameworks</h1>
            <p className="text-gray-400 text-sm mt-1">Build and manage your own compliance frameworks with custom controls</p>
          </div>
          <button onClick={() => setView('create')} className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm font-medium">
            + New Framework
          </button>
        </div>

        {frameworks.length === 0 ? (
          <div className="text-center py-20 text-gray-500">
            <div className="text-5xl mb-4">📋</div>
            <p className="text-lg">No custom frameworks yet</p>
            <p className="text-sm mt-2">Create one from a template or start from scratch</p>
            <button onClick={() => setView('create')} className="mt-4 bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded-lg text-sm">
              Create Framework
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {frameworks.map(fw => (
              <div key={fw.id} className="bg-gray-800 rounded-xl p-5 border border-gray-700 hover:border-blue-500 transition-colors">
                <div className="flex justify-between items-start mb-3">
                  <div className="flex-1">
                    <h3 className="font-semibold text-lg">{fw.name}</h3>
                    <p className="text-gray-400 text-sm mt-1 line-clamp-2">{fw.description}</p>
                  </div>
                  <span className={`ml-2 px-2 py-0.5 rounded-full text-xs font-medium ${
                    fw.status === 'published' ? 'bg-green-900 text-green-300' : 'bg-yellow-900 text-yellow-300'
                  }`}>{fw.status}</span>
                </div>

                <div className="grid grid-cols-3 gap-2 my-3">
                  <div className="text-center">
                    <div className="text-xl font-bold text-blue-400">{fw.control_count}</div>
                    <div className="text-xs text-gray-400">Controls</div>
                  </div>
                  <div className="text-center">
                    <div className="text-xl font-bold text-green-400">{fw.passing_controls}</div>
                    <div className="text-xs text-gray-400">Passing</div>
                  </div>
                  <div className="text-center">
                    <div className={`text-xl font-bold ${scoreColor(fw.compliance_score)}`}>{fw.compliance_score}%</div>
                    <div className="text-xs text-gray-400">Score</div>
                  </div>
                </div>

                <div className="flex gap-2 mt-4">
                  <button onClick={() => { setSelected(fw); setView('builder'); setEvaluation(null); }}
                    className="flex-1 bg-blue-700 hover:bg-blue-600 px-3 py-1.5 rounded text-sm">
                    Open
                  </button>
                  <button onClick={() => deleteFramework(fw.id)}
                    className="bg-red-900 hover:bg-red-800 px-3 py-1.5 rounded text-sm text-red-300">
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ── Create View ────────────────────────────────────────────────────────────
  if (view === 'create') {
    return (
      <div className="p-6 bg-gray-900 min-h-screen text-white max-w-2xl mx-auto">
        <button onClick={() => setView('list')} className="text-gray-400 hover:text-white mb-4 text-sm flex items-center gap-1">
          ← Back to Frameworks
        </button>
        <h2 className="text-xl font-bold mb-6">Create New Framework</h2>

        <div className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Framework Name *</label>
            <input value={newName} onChange={e => setNewName(e.target.value)}
              className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              placeholder="e.g. My Security Policy 2026" />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Description</label>
            <textarea value={newDesc} onChange={e => setNewDesc(e.target.value)}
              className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              rows={3} placeholder="Describe the purpose of this framework..." />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Start from Template</label>
            <div className="grid grid-cols-1 gap-2">
              {templates.map(t => (
                <label key={t.id} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                  newTemplate === t.id ? 'border-blue-500 bg-blue-900/20' : 'border-gray-600 bg-gray-800 hover:border-gray-400'
                }`}>
                  <input type="radio" name="template" value={t.id} checked={newTemplate === t.id}
                    onChange={() => setNewTemplate(t.id)} className="mt-0.5" />
                  <div>
                    <div className="font-medium text-sm">{t.name}</div>
                    <div className="text-gray-400 text-xs mt-0.5">{t.description}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div className="flex gap-3 pt-2">
            <button onClick={createFramework} disabled={loading || !newName.trim()}
              className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-4 py-2 rounded-lg font-medium">
              {loading ? 'Creating...' : 'Create Framework'}
            </button>
            <button onClick={() => setView('list')} className="px-4 py-2 rounded-lg border border-gray-600 hover:border-gray-400">
              Cancel
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Builder View ───────────────────────────────────────────────────────────
  if (view === 'builder' && selected) {
    return (
      <div className="p-6 bg-gray-900 min-h-screen text-white">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <button onClick={() => { setView('list'); setSelected(null); }} className="text-gray-400 hover:text-white text-sm">
              ← Back
            </button>
            <div>
              <h2 className="text-xl font-bold">{selected.name}</h2>
              <div className="flex items-center gap-2 mt-0.5">
                <span className={`px-2 py-0.5 rounded-full text-xs ${
                  selected.status === 'published' ? 'bg-green-900 text-green-300' : 'bg-yellow-900 text-yellow-300'
                }`}>{selected.status}</span>
                <span className="text-gray-400 text-xs">v{selected.version}</span>
                <span className="text-gray-400 text-xs">{selected.control_count} controls</span>
              </div>
            </div>
          </div>

          <div className="flex gap-2">
            <button onClick={evaluateFramework} disabled={loading}
              className="bg-purple-700 hover:bg-purple-600 px-4 py-2 rounded-lg text-sm">
              {loading ? 'Evaluating...' : 'Evaluate Compliance'}
            </button>
            {selected.status !== 'published' && (
              <button onClick={publishFramework} className="bg-green-700 hover:bg-green-600 px-4 py-2 rounded-lg text-sm">
                Publish
              </button>
            )}
          </div>
        </div>

        {evaluation && (
          <div className="bg-gray-800 rounded-xl p-4 mb-6 border border-purple-700">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold">Compliance Evaluation</h3>
              <span className={`text-2xl font-bold ${scoreColor(evaluation.overall_score)}`}>
                {evaluation.overall_score}%
              </span>
            </div>
            <div className="text-sm text-gray-400 mb-3">{evaluation.passing_controls} / {evaluation.total_controls} controls passing</div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {evaluation.domain_scores?.map((ds: any) => (
                <div key={ds.domain_id} className="bg-gray-700 rounded-lg p-2 text-xs">
                  <div className="font-medium truncate">{ds.domain_name}</div>
                  <div className={`font-bold ${scoreColor(ds.score)}`}>{ds.score}%</div>
                  <div className="text-gray-400">{ds.passing}/{ds.total}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-4">
          {selected.domains.map(domain => (
            <div key={domain.id} className="bg-gray-800 rounded-xl border border-gray-700">
              <div className="flex items-center justify-between p-4 border-b border-gray-700">
                <div>
                  <h3 className="font-semibold">{domain.name}</h3>
                  {domain.description && <p className="text-gray-400 text-sm">{domain.description}</p>}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-400">{domain.controls.length} controls</span>
                  <button onClick={() => setAddingControl(addingControl === domain.id ? null : domain.id)}
                    className="bg-blue-700 hover:bg-blue-600 px-3 py-1 rounded text-xs">
                    + Control
                  </button>
                </div>
              </div>

              {addingControl === domain.id && (
                <div className="p-4 bg-gray-750 border-b border-gray-700 space-y-3">
                  <h4 className="text-sm font-medium text-blue-300">Add Control to {domain.name}</h4>
                  <input value={controlForm.name} onChange={e => setControlForm(p => ({ ...p, name: e.target.value }))}
                    placeholder="Control name *" className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm text-white" />
                  <textarea value={controlForm.description} onChange={e => setControlForm(p => ({ ...p, description: e.target.value }))}
                    placeholder="Description" rows={2} className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm text-white" />
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">Severity</label>
                    <select value={controlForm.severity} onChange={e => setControlForm(p => ({ ...p, severity: e.target.value }))}
                      className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm text-white">
                      {['critical', 'high', 'medium', 'low'].map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">Evidence Sources (auto-assessment)</label>
                    <div className="flex flex-wrap gap-1">
                      {EVIDENCE_SOURCES.map(src => (
                        <button key={src} onClick={() => toggleEvidenceSource(src)}
                          className={`px-2 py-0.5 rounded text-xs transition-colors ${
                            controlForm.evidence_sources.includes(src)
                              ? 'bg-blue-600 text-white'
                              : 'bg-gray-600 text-gray-300 hover:bg-gray-500'
                          }`}>{src}</button>
                      ))}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => addControl(domain.id)} className="bg-blue-600 hover:bg-blue-700 px-3 py-1.5 rounded text-sm">
                      Add Control
                    </button>
                    <button onClick={() => setAddingControl(null)} className="text-gray-400 hover:text-white px-3 py-1.5 rounded text-sm border border-gray-600">
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {domain.controls.length === 0 ? (
                <div className="p-4 text-center text-gray-500 text-sm">No controls yet — add one above</div>
              ) : (
                <div className="divide-y divide-gray-700">
                  {domain.controls.map(ctrl => (
                    <div key={ctrl.id} className="p-4 flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono text-gray-400 bg-gray-700 px-1.5 py-0.5 rounded">{ctrl.id}</span>
                          <span className="font-medium">{ctrl.name}</span>
                          <span className={`text-xs ${SEVERITY_COLORS[ctrl.severity] || 'text-gray-400'}`}>{ctrl.severity}</span>
                        </div>
                        {ctrl.description && <p className="text-gray-400 text-sm mt-1">{ctrl.description}</p>}
                        {ctrl.evidence_sources?.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1.5">
                            {ctrl.evidence_sources.map(src => (
                              <span key={src} className="text-xs bg-blue-900/40 text-blue-300 px-1.5 py-0.5 rounded">{src}</span>
                            ))}
                          </div>
                        )}
                      </div>
                      <span className={`ml-3 text-xs px-2 py-0.5 rounded ${
                        ctrl.status === 'passing' ? 'bg-green-900 text-green-300' :
                        ctrl.status === 'failing' ? 'bg-red-900 text-red-300' :
                        'bg-gray-700 text-gray-400'
                      }`}>{ctrl.status}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}

          {addingDomain ? (
            <div className="bg-gray-800 rounded-xl border border-blue-600 p-4">
              <h3 className="text-sm font-medium text-blue-300 mb-3">Add Domain</h3>
              <input value={domainName} onChange={e => setDomainName(e.target.value)}
                placeholder="Domain name (e.g. Access Control)" autoFocus
                className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white mb-3" />
              <div className="flex gap-2">
                <button onClick={addDomain} className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm">
                  Add Domain
                </button>
                <button onClick={() => setAddingDomain(false)} className="text-gray-400 hover:text-white px-4 py-2 rounded border border-gray-600 text-sm">
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button onClick={() => setAddingDomain(true)}
              className="w-full border-2 border-dashed border-gray-600 hover:border-blue-500 rounded-xl p-4 text-gray-400 hover:text-blue-400 transition-colors text-sm">
              + Add Domain
            </button>
          )}
        </div>
      </div>
    );
  }

  return null;
}
