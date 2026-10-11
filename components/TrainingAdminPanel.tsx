import React, { useEffect, useState } from 'react';
import { authFetch } from '../services/apiService';
import { Plus, Trash2, Send } from 'lucide-react';

interface ModuleSummary {
    id: string;
    title: string;
    description: string;
    duration_minutes: number;
    quiz_questions: { question: string; options: string[] }[];
}

interface AssignmentRow {
    id: string;
    user_email: string;
    module_title: string;
    status: string;
    quiz_score: number | null;
    attempts?: number;
    completed_at: string | null;
}

interface DraftQuestion { question: string; options: string; correct_answer: string }

const emptyQuestion = (): DraftQuestion => ({ question: '', options: '', correct_answer: '' });
const input = 'w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-900 dark:text-white';
const card = 'bg-white dark:bg-[#0f1115] rounded-xl border border-gray-200 dark:border-gray-800 p-6 space-y-4';

// Options are entered one per line; the correct answer must match one of them
export const toQuizPayload = (draft: DraftQuestion[]) =>
    draft
        .filter(q => q.question.trim())
        .map(q => ({
            question: q.question.trim(),
            options: q.options.split('\n').map(o => o.trim()).filter(Boolean),
            correct_answer: q.correct_answer.trim(),
        }));

export default function TrainingAdminPanel() {
    const [modules, setModules] = useState<ModuleSummary[]>([]);
    const [assignments, setAssignments] = useState<AssignmentRow[]>([]);
    const [form, setForm] = useState({ title: '', description: '', content_url: '', duration_minutes: 15 });
    const [questions, setQuestions] = useState<DraftQuestion[]>([]);
    const [assign, setAssign] = useState({ user_email: '', module_id: '' });
    const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

    const load = async () => {
        const [m, a] = await Promise.all([authFetch('/api/training/modules'), authFetch('/api/training/assignments')]);
        if (m.ok) setModules(await m.json());
        if (a.ok) setAssignments(await a.json());
    };

    useEffect(() => { load(); }, []);

    const report = async (res: Response, okText: string) => {
        if (res.ok) {
            setMessage({ ok: true, text: okText });
            await load();
            return true;
        }
        const body = await res.json().catch(() => ({}));
        const detail = typeof body.detail === 'string' ? body.detail : `Request failed (HTTP ${res.status})`;
        setMessage({ ok: false, text: detail });
        return false;
    };

    const createModule = async () => {
        const res = await authFetch('/api/training/modules', {
            method: 'POST',
            body: JSON.stringify({ ...form, quiz_questions: toQuizPayload(questions) }),
        });
        if (await report(res, `Module “${form.title}” created`)) {
            setForm({ title: '', description: '', content_url: '', duration_minutes: 15 });
            setQuestions([]);
        }
    };

    const assignModule = async () => {
        const res = await authFetch('/api/training/assign', { method: 'POST', body: JSON.stringify(assign) });
        if (await report(res, `Assigned to ${assign.user_email}`)) setAssign({ user_email: '', module_id: assign.module_id });
    };

    const setQuestion = (i: number, patch: Partial<DraftQuestion>) =>
        setQuestions(prev => prev.map((q, j) => (j === i ? { ...q, ...patch } : q)));

    return (
        <div className="space-y-6">
            {message && (
                <p className={`text-sm ${message.ok ? 'text-green-600' : 'text-red-600'}`}>{message.text}</p>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className={card}>
                    <h3 className="font-semibold text-gray-900 dark:text-white">Create module</h3>
                    <input className={input} placeholder="Title" value={form.title}
                        onChange={e => setForm({ ...form, title: e.target.value })} />
                    <textarea className={input} placeholder="Description" rows={2} value={form.description}
                        onChange={e => setForm({ ...form, description: e.target.value })} />
                    <input className={input} placeholder="Training material URL (video, slides, document)" value={form.content_url}
                        onChange={e => setForm({ ...form, content_url: e.target.value })} />
                    <label className="block text-sm text-gray-600 dark:text-gray-300">
                        Duration (minutes)
                        <input className={input} type="number" min={0} value={form.duration_minutes}
                            onChange={e => setForm({ ...form, duration_minutes: Number(e.target.value) })} />
                    </label>

                    {questions.map((q, i) => (
                        <div key={i} className="p-3 rounded-lg border border-gray-200 dark:border-gray-700 space-y-2">
                            <div className="flex justify-between items-center">
                                <span className="text-xs font-semibold text-gray-500">Question {i + 1}</span>
                                <button aria-label={`Remove question ${i + 1}`} onClick={() => setQuestions(prev => prev.filter((_, j) => j !== i))}>
                                    <Trash2 className="w-4 h-4 text-gray-400 hover:text-red-500" />
                                </button>
                            </div>
                            <input className={input} placeholder="Question" value={q.question}
                                onChange={e => setQuestion(i, { question: e.target.value })} />
                            <textarea className={input} rows={3} placeholder="Options, one per line" value={q.options}
                                onChange={e => setQuestion(i, { options: e.target.value })} />
                            <input className={input} placeholder="Correct answer (must match an option)" value={q.correct_answer}
                                onChange={e => setQuestion(i, { correct_answer: e.target.value })} />
                        </div>
                    ))}
                    <div className="flex gap-2">
                        <button onClick={() => setQuestions(prev => [...prev, emptyQuestion()])}
                            className="px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-700 flex items-center gap-1 text-gray-700 dark:text-gray-200">
                            <Plus className="w-4 h-4" /> Add quiz question
                        </button>
                        <button onClick={createModule} disabled={!form.title.trim()}
                            className="px-4 py-2 text-sm rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white">
                            Create module
                        </button>
                    </div>
                </div>

                <div className={card}>
                    <h3 className="font-semibold text-gray-900 dark:text-white">Assign module</h3>
                    <select className={input} value={assign.module_id} onChange={e => setAssign({ ...assign, module_id: e.target.value })}>
                        <option value="">Select a module…</option>
                        {modules.map(m => <option key={m.id} value={m.id}>{m.title}</option>)}
                    </select>
                    <input className={input} type="email" placeholder="User email" value={assign.user_email}
                        onChange={e => setAssign({ ...assign, user_email: e.target.value })} />
                    <button onClick={assignModule} disabled={!assign.module_id || !assign.user_email.trim()}
                        className="px-4 py-2 text-sm rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white flex items-center gap-1">
                        <Send className="w-4 h-4" /> Assign
                    </button>
                    <div className="text-xs text-gray-500">
                        {modules.length} module{modules.length === 1 ? '' : 's'} available
                    </div>
                </div>
            </div>

            <div className={card}>
                <h3 className="font-semibold text-gray-900 dark:text-white">Assignments</h3>
                {assignments.length === 0 ? (
                    <p className="text-sm text-gray-500">No assignments yet.</p>
                ) : (
                    <table className="w-full text-sm text-left">
                        <thead className="text-xs uppercase text-gray-500">
                            <tr><th className="py-2">User</th><th>Module</th><th>Status</th><th>Score</th><th>Attempts</th></tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-gray-800 text-gray-700 dark:text-gray-300">
                            {assignments.map(a => (
                                <tr key={a.id}>
                                    <td className="py-2">{a.user_email}</td>
                                    <td>{a.module_title}</td>
                                    <td>{a.status}</td>
                                    <td>{a.quiz_score === null ? '—' : `${a.quiz_score}%`}</td>
                                    <td>{a.attempts ?? 0}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}
