import React, { useState, useEffect, useCallback } from 'react';
import { ClipboardCheck, Plus, AlertTriangle, ChevronRight, FileText, CheckCircle, ArrowRight } from 'lucide-react';

interface Finding {
  id: string;
  title: string;
  severity: string;
  status: string;
  recommendation: string;
  managementResponse: string;
  controlId: string;
}

interface AuditProgram {
  id: string;
  name: string;
  description: string;
  framework: string;
  type: string;
  status: string;
  auditor: string;
  auditee: string;
  startDate: string;
  endDate: string;
  findings: Finding[];
  created_at: string;
}

interface Report {
  totalFindings: number;
  findingsBySeverity: Record<string, number>;
  findingsByStatus: Record<string, number>;
  openFindings: number;
  resolvedFindings: number;
}

const STATUS_COLORS: Record<string, string> = {
  Planning: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
  Fieldwork: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  Review: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  Remediation: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  Closed: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
};

const SEV_COLORS: Record<string, string> = {
  Critical: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  High: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  Medium: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  Low: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  Informational: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
};

const STATUS_TRANSITIONS: Record<string, string[]> = {
  Planning: ['Fieldwork'],
  Fieldwork: ['Review', 'Planning'],
  Review: ['Remediation', 'Fieldwork', 'Closed'],
  Remediation: ['Review', 'Closed'],
  Closed: [],
};

const authHeader = () => ({ Authorization: `Bearer ${sessionStorage.getItem('token')}`, 'Content-Type': 'application/json' });

export default function AuditProgramDashboard() {
  const [programs, setPrograms] = useState<AuditProgram[]>([]);
  const [selected, setSelected] = useState<AuditProgram | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [view, setView] = useState<'list' | 'create' | 'detail'>('list');
  const [loading, setLoading] = useState(true);
  const [newProgram, setNewProgram] = useState({ name: '', description: '', framework: '', type: 'Internal', auditor: '', auditee: '', startDate: '', endDate: '' });
  const [newFinding, setNewFinding] = useState({ title: '', description: '', severity: 'Medium', controlId: '', recommendation: '' });
  const [showFindingForm, setShowFindingForm] = useState(false);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/audit-programs', { headers: authHeader() });
      if (res.ok) setPrograms(await res.json());
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchList(); }, [fetchList]);

  const openDetail = async (p: AuditProgram) => {
    setSelected(p);
    const res = await fetch(`/api/audit-programs/${p.id}/report`, { headers: authHeader() });
    if (res.ok) setReport(await res.json());
    setView('detail');
  };

  const create = async () => {
    if (!newProgram.name.trim()) return;
    const res = await fetch('/api/audit-programs', { method: 'POST', headers: authHeader(), body: JSON.stringify(newProgram) });
    if (res.ok) { await fetchList(); setView('list'); setNewProgram({ name: '', description: '', framework: '', type: 'Internal', auditor: '', auditee: '', startDate: '', endDate: '' }); }
  };

  const transition = async (newStatus: string) => {
    if (!selected) return;
    const res = await fetch(`/api/audit-programs/${selected.id}/status`, { method: 'PUT', headers: authHeader(), body: JSON.stringify({ status: newStatus }) });
    if (res.ok) { const updated = await res.json(); setSelected(updated); await fetchList(); }
  };

  const addFinding = async () => {
    if (!selected || !newFinding.title.trim()) return;
    const res = await fetch(`/api/audit-programs/${selected.id}/findings`, { method: 'POST', headers: authHeader(), body: JSON.stringify(newFinding) });
    if (res.ok) {
      const updated = await res.json();
      setSelected(updated);
      setNewFinding({ title: '', description: '', severity: 'Medium', controlId: '', recommendation: '' });
      setShowFindingForm(false);
    }
  };

  if (view === 'create') return (
    <div className="space-y-6 max-w-xl">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white">New Audit Program</h2>
        <button onClick={() => setView('list')} className="text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">Cancel</button>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <input value={newProgram.name} onChange={e => setNewProgram(p => ({ ...p, name: e.target.value }))} placeholder="Name *" className="col-span-2 px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg text-sm" />
        <input value={newProgram.description} onChange={e => setNewProgram(p => ({ ...p, description: e.target.value }))} placeholder="Description" className="col-span-2 px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg text-sm" />
        <input value={newProgram.framework} onChange={e => setNewProgram(p => ({ ...p, framework: e.target.value }))} placeholder="Framework (e.g. ISO 27001)" className="px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg text-sm" />
        <select value={newProgram.type} onChange={e => setNewProgram(p => ({ ...p, type: e.target.value }))} className="px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg text-sm">
          {['Internal', 'External', 'Regulatory', 'Certification'].map(t => <option key={t}>{t}</option>)}
        </select>
        <input value={newProgram.auditor} onChange={e => setNewProgram(p => ({ ...p, auditor: e.target.value }))} placeholder="Auditor" className="px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg text-sm" />
        <input value={newProgram.auditee} onChange={e => setNewProgram(p => ({ ...p, auditee: e.target.value }))} placeholder="Auditee" className="px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg text-sm" />
        <div><label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Start Date</label><input type="date" value={newProgram.startDate} onChange={e => setNewProgram(p => ({ ...p, startDate: e.target.value }))} className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg text-sm" /></div>
        <div><label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">End Date</label><input type="date" value={newProgram.endDate} onChange={e => setNewProgram(p => ({ ...p, endDate: e.target.value }))} className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg text-sm" /></div>
      </div>
      <button onClick={create} disabled={!newProgram.name.trim()} className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 text-sm">Create Audit Program</button>
    </div>
  );

  if (view === 'detail' && selected) return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <button onClick={() => setView('list')} className="text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">← Back</button>
        <ChevronRight className="w-4 h-4 text-gray-400" />
        <span className="text-sm font-medium text-gray-900 dark:text-white">{selected.name}</span>
        <span className={`ml-1 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[selected.status]}`}>{selected.status}</span>
      </div>

      {STATUS_TRANSITIONS[selected.status]?.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          <span className="text-xs text-gray-500 dark:text-gray-400 self-center">Transition to:</span>
          {STATUS_TRANSITIONS[selected.status].map(s => (
            <button key={s} onClick={() => transition(s)} className={`flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg border ${STATUS_COLORS[s]} border-current`}>
              <ArrowRight className="w-3 h-3" /> {s}
            </button>
          ))}
        </div>
      )}

      {report && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[{ label: 'Total Findings', value: report.totalFindings }, { label: 'Open', value: report.openFindings }, { label: 'Resolved', value: report.resolvedFindings }, { label: 'Critical', value: report.findingsBySeverity?.Critical || 0 }].map(({ label, value }) => (
            <div key={label} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
              <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">{value}</p>
            </div>
          ))}
        </div>
      )}

      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-medium text-gray-900 dark:text-white flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-orange-500" /> Findings ({selected.findings.length})</h3>
          <button onClick={() => setShowFindingForm(v => !v)} className="flex items-center gap-1 text-sm text-primary-600 hover:text-primary-700 dark:text-primary-400"><Plus className="w-4 h-4" /> Add Finding</button>
        </div>
        {showFindingForm && (
          <div className="mb-4 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg space-y-2">
            <input value={newFinding.title} onChange={e => setNewFinding(f => ({ ...f, title: e.target.value }))} placeholder="Finding title *" className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg" />
            <textarea value={newFinding.description} onChange={e => setNewFinding(f => ({ ...f, description: e.target.value }))} placeholder="Description" rows={2} className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg" />
            <div className="flex gap-2">
              <select value={newFinding.severity} onChange={e => setNewFinding(f => ({ ...f, severity: e.target.value }))} className="text-sm px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg">
                {['Critical', 'High', 'Medium', 'Low', 'Informational'].map(s => <option key={s}>{s}</option>)}
              </select>
              <input value={newFinding.controlId} onChange={e => setNewFinding(f => ({ ...f, controlId: e.target.value }))} placeholder="Control ID" className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg" />
            </div>
            <button onClick={addFinding} disabled={!newFinding.title.trim()} className="px-3 py-1.5 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50">Add</button>
          </div>
        )}
        {selected.findings.length === 0 ? (
          <p className="text-sm text-gray-400 dark:text-gray-500 text-center py-4">No findings yet.</p>
        ) : (
          <div className="space-y-2">
            {selected.findings.map(f => (
              <div key={f.id} className="flex items-start gap-3 p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg">
                <span className={`px-2 py-0.5 text-xs rounded-full font-medium mt-0.5 shrink-0 ${SEV_COLORS[f.severity]}`}>{f.severity}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 dark:text-white">{f.title}</p>
                  {f.recommendation && <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{f.recommendation}</p>}
                </div>
                <span className="text-xs text-gray-400 shrink-0">{f.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <ClipboardCheck className="w-5 h-5 text-primary-500" /> Audit Programs
        </h2>
        <button onClick={() => setView('create')} className="flex items-center gap-2 px-3 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700">
          <Plus className="w-4 h-4" /> New Program
        </button>
      </div>
      {loading ? (
        <div className="flex justify-center py-12"><div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" /></div>
      ) : programs.length === 0 ? (
        <div className="text-center py-16 text-gray-400 dark:text-gray-500">No audit programs yet.</div>
      ) : (
        <div className="grid gap-4">
          {programs.map(p => (
            <button key={p.id} onClick={() => openDetail(p)} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 flex items-center justify-between hover:shadow-md transition-shadow text-left w-full">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="font-medium text-gray-900 dark:text-white">{p.name}</h3>
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[p.status]}`}>{p.status}</span>
                  {p.framework && <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded-full text-xs">{p.framework}</span>}
                </div>
                <div className="flex gap-4 text-xs text-gray-400">
                  <span>{p.type}</span>
                  <span>{p.auditor && `Auditor: ${p.auditor}`}</span>
                  <span>{p.findings.length} findings</span>
                </div>
              </div>
              <ChevronRight className="w-4 h-4 text-gray-400 ml-4 shrink-0" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
