import React, { useState, useEffect, useCallback } from 'react';
import { ClipboardList, Plus, Send, Eye, Trash2, ChevronRight, Users, CheckCircle, Clock } from 'lucide-react';

interface Question {
  id: string;
  text: string;
  type: 'text' | 'yes_no' | 'multiple_choice' | 'scale';
  required: boolean;
  options?: string[];
}

interface Questionnaire {
  id: string;
  title: string;
  description: string;
  type: string;
  status: 'Draft' | 'Active' | 'Closed';
  questions: Question[];
  responseCount: number;
  createdBy: string;
  created_at: string;
}

interface QStats { total: number; submitted: number; pending: number; responseRate: number; }

const STATUS_BADGE: Record<string, string> = {
  Draft: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
  Active: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  Closed: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
};

const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}`, 'Content-Type': 'application/json' });

export default function QuestionnaireEngine() {
  const [questionnaires, setQuestionnaires] = useState<Questionnaire[]>([]);
  const [selected, setSelected] = useState<Questionnaire | null>(null);
  const [stats, setStats] = useState<QStats | null>(null);
  const [view, setView] = useState<'list' | 'create' | 'detail'>('list');
  const [loading, setLoading] = useState(true);
  const [sendEmails, setSendEmails] = useState('');
  const [sending, setSending] = useState(false);
  const [newQ, setNewQ] = useState({ title: '', description: '', type: 'Internal', questions: [] as Question[] });

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/questionnaires', { headers: authHeader() });
      if (res.ok) setQuestionnaires(await res.json());
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchList(); }, [fetchList]);

  const openDetail = async (q: Questionnaire) => {
    setSelected(q);
    const res = await fetch(`/api/questionnaires/${q.id}/stats`, { headers: authHeader() });
    if (res.ok) setStats(await res.json());
    setView('detail');
  };

  const createQuestionnaire = async () => {
    if (!newQ.title.trim()) return;
    const res = await fetch('/api/questionnaires', { method: 'POST', headers: authHeader(), body: JSON.stringify(newQ) });
    if (res.ok) { await fetchList(); setView('list'); setNewQ({ title: '', description: '', type: 'Internal', questions: [] }); }
  };

  const sendQuestionnaire = async () => {
    if (!selected || !sendEmails.trim()) return;
    setSending(true);
    const emails = sendEmails.split(/[\n,;]+/).map(e => e.trim()).filter(Boolean);
    try {
      const res = await fetch(`/api/questionnaires/${selected.id}/send`, { method: 'POST', headers: authHeader(), body: JSON.stringify({ emails }) });
      if (res.ok) { setSendEmails(''); await fetchList(); }
    } finally { setSending(false); }
  };

  const deleteQuestionnaire = async (id: string) => {
    if (!confirm('Delete this questionnaire?')) return;
    await fetch(`/api/questionnaires/${id}`, { method: 'DELETE', headers: authHeader() });
    await fetchList();
    if (selected?.id === id) { setSelected(null); setView('list'); }
  };

  const addQuestion = () => {
    const q: Question = { id: crypto.randomUUID(), text: '', type: 'text', required: false };
    setNewQ(prev => ({ ...prev, questions: [...prev.questions, q] }));
  };

  const updateQuestion = (idx: number, patch: Partial<Question>) => {
    setNewQ(prev => ({ ...prev, questions: prev.questions.map((q, i) => i === idx ? { ...q, ...patch } : q) }));
  };

  if (view === 'create') return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white">New Questionnaire</h2>
        <button onClick={() => setView('list')} className="text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">Cancel</button>
      </div>
      <div className="space-y-4">
        <input value={newQ.title} onChange={e => setNewQ(p => ({ ...p, title: e.target.value }))} placeholder="Title *" className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg" />
        <textarea value={newQ.description} onChange={e => setNewQ(p => ({ ...p, description: e.target.value }))} placeholder="Description" rows={2} className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg" />
        <select value={newQ.type} onChange={e => setNewQ(p => ({ ...p, type: e.target.value }))} className="px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg">
          {['Internal', 'Vendor', 'Gap Analysis', 'Security Assessment', 'Audit'].map(t => <option key={t}>{t}</option>)}
        </select>
      </div>
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-medium text-gray-900 dark:text-white">Questions</h3>
          <button onClick={addQuestion} className="flex items-center gap-1 text-sm text-primary-600 hover:text-primary-700"><Plus className="w-4 h-4" /> Add Question</button>
        </div>
        {newQ.questions.map((q, idx) => (
          <div key={q.id} className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3 space-y-2">
            <input value={q.text} onChange={e => updateQuestion(idx, { text: e.target.value })} placeholder={`Question ${idx + 1}`} className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded" />
            <div className="flex gap-2">
              <select value={q.type} onChange={e => updateQuestion(idx, { type: e.target.value as any })} className="text-xs px-2 py-1 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 rounded">
                {['text', 'yes_no', 'multiple_choice', 'scale'].map(t => <option key={t}>{t}</option>)}
              </select>
              <label className="flex items-center gap-1 text-xs text-gray-600 dark:text-gray-400">
                <input type="checkbox" checked={q.required} onChange={e => updateQuestion(idx, { required: e.target.checked })} /> Required
              </label>
            </div>
          </div>
        ))}
      </div>
      <button onClick={createQuestionnaire} disabled={!newQ.title.trim()} className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50">Create Questionnaire</button>
    </div>
  );

  if (view === 'detail' && selected) return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <button onClick={() => setView('list')} className="text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">← Back</button>
        <ChevronRight className="w-4 h-4 text-gray-400" />
        <span className="text-sm font-medium text-gray-900 dark:text-white">{selected.title}</span>
        <span className={`ml-2 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_BADGE[selected.status]}`}>{selected.status}</span>
      </div>
      {stats && (
        <div className="grid grid-cols-4 gap-4">
          {[{ label: 'Sent To', value: stats.total, icon: Users }, { label: 'Submitted', value: stats.submitted, icon: CheckCircle }, { label: 'Pending', value: stats.pending, icon: Clock }, { label: 'Response Rate', value: `${stats.responseRate}%`, icon: ClipboardList }].map(({ label, value, icon: Icon }) => (
            <div key={label} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 text-xs mb-1"><Icon className="w-3.5 h-3.5" />{label}</div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
            </div>
          ))}
        </div>
      )}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <h3 className="font-medium text-gray-900 dark:text-white mb-3">Send to Respondents</h3>
        <textarea value={sendEmails} onChange={e => setSendEmails(e.target.value)} placeholder="Enter email addresses (comma or newline separated)" rows={3} className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg mb-3" />
        <button onClick={sendQuestionnaire} disabled={sending || !sendEmails.trim()} className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 text-sm">
          <Send className="w-4 h-4" />{sending ? 'Sending…' : 'Send'}
        </button>
      </div>
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <h3 className="font-medium text-gray-900 dark:text-white mb-3">Questions ({selected.questions.length})</h3>
        <ol className="space-y-2">
          {selected.questions.map((q, i) => (
            <li key={q.id} className="text-sm text-gray-700 dark:text-gray-300 flex gap-2">
              <span className="text-gray-400 w-5">{i + 1}.</span>
              <span>{q.text} <span className="text-xs text-gray-400">({q.type}){q.required && ' *'}</span></span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <ClipboardList className="w-5 h-5 text-primary-500" /> Questionnaires
        </h2>
        <button onClick={() => setView('create')} className="flex items-center gap-2 px-3 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700">
          <Plus className="w-4 h-4" /> New Questionnaire
        </button>
      </div>
      {loading ? (
        <div className="flex justify-center py-12"><div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" /></div>
      ) : questionnaires.length === 0 ? (
        <div className="text-center py-16 text-gray-400 dark:text-gray-500">No questionnaires yet. Create one to get started.</div>
      ) : (
        <div className="grid gap-4">
          {questionnaires.map(q => (
            <div key={q.id} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 flex items-start justify-between hover:shadow-md transition-shadow">
              <button onClick={() => openDetail(q)} className="flex-1 text-left">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="font-medium text-gray-900 dark:text-white">{q.title}</h3>
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_BADGE[q.status]}`}>{q.status}</span>
                  <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded-full text-xs">{q.type}</span>
                </div>
                {q.description && <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">{q.description}</p>}
                <div className="flex gap-4 text-xs text-gray-400">
                  <span>{q.questions.length} questions</span>
                  <span>{q.responseCount} responses</span>
                </div>
              </button>
              <div className="flex gap-2 ml-4">
                <button onClick={() => openDetail(q)} className="p-1.5 text-gray-400 hover:text-primary-500"><Eye className="w-4 h-4" /></button>
                <button onClick={() => deleteQuestionnaire(q.id)} className="p-1.5 text-gray-400 hover:text-red-500"><Trash2 className="w-4 h-4" /></button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
