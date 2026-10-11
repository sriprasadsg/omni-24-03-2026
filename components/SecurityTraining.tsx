import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';
import { BookOpen, CheckCircle, Clock, Trophy, Award, ExternalLink } from 'lucide-react';
import TrainingAdminPanel from './TrainingAdminPanel';

interface UserProgress {
    id: string;
    module_id: string;
    module_title: string;
    module_description: string;
    duration_minutes: number;
    status: 'Assigned' | 'In Progress' | 'Completed';
    started_at: string | null;
    completed_at: string | null;
    quiz_score: number | null;
    attempts?: number;
    content_url?: string;
    // Questions and options only — the server keeps the answers and grades
    quiz_questions?: { question: string; options: string[] }[];
}

type QuizResult = { quiz_score: number; passed: boolean; pass_mark: number };

export default function SecurityTraining() {
    const [view, setView] = useState<'my-training' | 'admin'>('my-training');
    const [assignments, setAssignments] = useState<UserProgress[]>([]);
    const [selectedModule, setSelectedModule] = useState<UserProgress | null>(null);
    const [loading, setLoading] = useState(true);
    const [answers, setAnswers] = useState<string[]>([]);
    const [quizResult, setQuizResult] = useState<QuizResult | null>(null);
    const [actionError, setActionError] = useState('');

    useEffect(() => {
        if (view === 'my-training') fetchMyTraining();
    }, [view]);

    const fetchMyTraining = async () => {
        try {
            const res = await authFetch('/api/training/my-training');
            if (res.ok) setAssignments(await res.json());
        } catch (error) {
            console.error("Error fetching training", error);
        } finally {
            setLoading(false);
        }
    };

    const startModule = async (assignment: UserProgress) => {
        if (assignment.status === 'Assigned') {
            try {
                await authFetch(`/api/training/progress/${assignment.id}`, {
                    method: 'PUT',
                    body: JSON.stringify({ status: 'In Progress' })
                });
                // Optimistic update
                setAssignments(prev => prev.map(a => a.id === assignment.id ? { ...a, status: 'In Progress' } : a));
            } catch (error) {
                console.error("Error starting module", error);
            }
        }
        setAnswers([]);
        setQuizResult(null);
        setActionError('');
        setSelectedModule(assignment);
    };

    const replaceAssignment = (updated: UserProgress) =>
        setAssignments(prev => prev.map(a => a.id === updated.id ? { ...a, ...updated } : a));

    // Modules without a quiz are completed directly
    const completeModule = async (assignmentId: string) => {
        setActionError('');
        const res = await authFetch(`/api/training/progress/${assignmentId}`, {
            method: 'PUT',
            body: JSON.stringify({ status: 'Completed' }),
        });
        if (!res.ok) { setActionError((await res.json().catch(() => ({}))).detail || 'Could not complete the module'); return; }
        replaceAssignment(await res.json());
        setSelectedModule(null);
    };

    // Quiz modules: the server grades the answers and records the score
    const submitQuiz = async (assignmentId: string) => {
        setActionError('');
        const res = await authFetch(`/api/training/progress/${assignmentId}/quiz`, {
            method: 'POST',
            body: JSON.stringify({ answers }),
        });
        const body = await res.json().catch(() => ({}));
        if (!res.ok) { setActionError(body.detail || 'Could not submit the quiz'); return; }
        replaceAssignment(body);
        setQuizResult(body);
    };

    return (
        <div className="p-6 max-w-7xl mx-auto space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold bg-gradient-to-r from-indigo-500 to-purple-600 bg-clip-text text-transparent">
                        Security Awareness Training
                    </h1>
                    <p className="text-gray-500 dark:text-gray-400">
                        Stay ahead of threats with interactive learning modules.
                    </p>
                </div>
                <div className="flex bg-gray-100 dark:bg-gray-800 p-1 rounded-lg">
                    <button
                        onClick={() => setView('my-training')}
                        className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${view === 'my-training'
                                ? 'bg-white dark:bg-gray-700 text-indigo-600 dark:text-indigo-400 shadow-sm'
                                : 'text-gray-500 dark:text-gray-400'
                            }`}
                    >
                        My Training
                    </button>
                    <button
                        onClick={() => setView('admin')}
                        className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${view === 'admin'
                                ? 'bg-white dark:bg-gray-700 text-indigo-600 dark:text-indigo-400 shadow-sm'
                                : 'text-gray-500 dark:text-gray-400'
                            }`}
                    >
                        Admin
                    </button>
                </div>
            </div>

            {view === 'my-training' ? (
                <>
                    {/* Stats */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="bg-indigo-50 dark:bg-indigo-900/20 p-4 rounded-xl border border-indigo-100 dark:border-indigo-900/30 flex items-center gap-4">
                            <div className="p-3 bg-indigo-100 dark:bg-indigo-900/50 rounded-lg text-indigo-600 dark:text-indigo-400">
                                <Trophy className="w-6 h-6" />
                            </div>
                            <div>
                                <div className="text-2xl font-bold text-gray-900 dark:text-white">
                                    {assignments.filter(a => a.status === 'Completed').length}
                                </div>
                                <div className="text-xs text-gray-500">Modules Completed</div>
                            </div>
                        </div>
                        <div className="bg-orange-50 dark:bg-orange-900/20 p-4 rounded-xl border border-orange-100 dark:border-orange-900/30 flex items-center gap-4">
                            <div className="p-3 bg-orange-100 dark:bg-orange-900/50 rounded-lg text-orange-600 dark:text-orange-400">
                                <Clock className="w-6 h-6" />
                            </div>
                            <div>
                                <div className="text-2xl font-bold text-gray-900 dark:text-white">
                                    {assignments.filter(a => a.status !== 'Completed').length}
                                </div>
                                <div className="text-xs text-gray-500">Pending Assignments</div>
                            </div>
                        </div>
                    </div>

                    {/* Module List */}
                    <div className="grid grid-cols-1 gap-4">
                        {!loading && assignments.length === 0 && (
                            <div className="p-8 text-center text-gray-500 bg-white dark:bg-[#0f1115] rounded-xl border border-gray-200 dark:border-gray-800">
                                No training assigned to you yet.
                            </div>
                        )}
                        {assignments.map(assignment => (
                            <div key={assignment.id} className="bg-white dark:bg-[#0f1115] p-6 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                                <div className="flex items-start gap-4">
                                    <div className={`p-3 rounded-lg ${assignment.status === 'Completed' ? 'bg-green-100 text-green-600' : 'bg-indigo-100 text-indigo-600'
                                        }`}>
                                        {assignment.status === 'Completed' ? <CheckCircle className="w-6 h-6" /> : <BookOpen className="w-6 h-6" />}
                                    </div>
                                    <div>
                                        <h3 className="font-semibold text-lg text-gray-900 dark:text-white">{assignment.module_title}</h3>
                                        <p className="text-gray-500 dark:text-gray-400 text-sm mb-2">{assignment.module_description}</p>
                                        <div className="flex items-center gap-4 text-xs text-gray-400">
                                            <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {assignment.duration_minutes} mins</span>
                                            <span className={`px-2 py-0.5 rounded-full ${assignment.status === 'Completed' ? 'bg-green-50 text-green-600' :
                                                    assignment.status === 'In Progress' ? 'bg-blue-50 text-blue-600' : 'bg-gray-100 text-gray-600'
                                                }`}>
                                                {assignment.status}
                                            </span>
                                            {assignment.quiz_score !== null && (
                                                <span className="flex items-center gap-1 text-green-600"><Award className="w-3 h-3" /> Score: {assignment.quiz_score}%</span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                                <button
                                    onClick={() => startModule(assignment)}
                                    className={`px-6 py-2 rounded-lg font-medium transition-colors ${assignment.status === 'Completed'
                                            ? 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                                            : 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-lg shadow-indigo-500/20'
                                        }`}
                                >
                                    {assignment.status === 'Completed' ? 'Review' : assignment.status === 'In Progress' ? 'Continue' : 'Start'}
                                </button>
                            </div>
                        ))}
                    </div>

                    {/* Player Modal */}
                    {selectedModule && (
                        <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50">
                            <div className="bg-white dark:bg-gray-900 rounded-xl w-full max-w-3xl max-h-[90vh] overflow-y-auto shadow-2xl">
                                <div className="p-4 border-b border-gray-200 dark:border-gray-800 flex justify-between items-center bg-gray-50 dark:bg-gray-800">
                                    <h3 className="font-bold text-gray-900 dark:text-white">{selectedModule.module_title}</h3>
                                    <button onClick={() => setSelectedModule(null)} className="text-gray-500 hover:text-gray-700">Close</button>
                                </div>
                                <div className="p-6 space-y-6">
                                    <p className="text-sm text-gray-600 dark:text-gray-300">{selectedModule.module_description}</p>
                                    {selectedModule.content_url ? (
                                        <a href={selectedModule.content_url} target="_blank" rel="noopener noreferrer"
                                            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium">
                                            <ExternalLink className="w-4 h-4" /> Open training material
                                        </a>
                                    ) : (
                                        <p className="text-sm text-gray-500">This module has no linked material.</p>
                                    )}

                                    {(selectedModule.quiz_questions?.length || 0) > 0 ? (
                                        <div className="space-y-4">
                                            <h4 className="font-semibold text-gray-900 dark:text-white">Quiz</h4>
                                            {selectedModule.quiz_questions!.map((q, qi) => (
                                                <fieldset key={qi} className="space-y-2">
                                                    <legend className="text-sm font-medium text-gray-800 dark:text-gray-200">{qi + 1}. {q.question}</legend>
                                                    {q.options.map(opt => (
                                                        <label key={opt} className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                                                            <input type="radio" name={`q-${qi}`} value={opt} checked={answers[qi] === opt}
                                                                onChange={() => setAnswers(prev => { const next = [...prev]; next[qi] = opt; return next; })} />
                                                            {opt}
                                                        </label>
                                                    ))}
                                                </fieldset>
                                            ))}
                                            {quizResult && (
                                                <p className={`text-sm font-medium ${quizResult.passed ? 'text-green-600' : 'text-amber-600'}`}>
                                                    Score {quizResult.quiz_score}% — {quizResult.passed ? 'passed, module completed.' : `below the ${quizResult.pass_mark}% pass mark. Review the material and try again.`}
                                                </p>
                                            )}
                                            <button
                                                onClick={() => submitQuiz(selectedModule.id)}
                                                disabled={selectedModule.status === 'Completed' || answers.filter(Boolean).length < (selectedModule.quiz_questions?.length || 0)}
                                                className="px-6 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white rounded-lg flex items-center gap-2"
                                            >
                                                <CheckCircle className="w-4 h-4" /> Submit answers
                                            </button>
                                        </div>
                                    ) : (
                                        <button
                                            onClick={() => completeModule(selectedModule.id)}
                                            disabled={selectedModule.status === 'Completed'}
                                            className="px-6 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white rounded-lg flex items-center gap-2"
                                        >
                                            <CheckCircle className="w-4 h-4" /> Mark as Complete
                                        </button>
                                    )}
                                    {actionError && <p className="text-sm text-red-600">{actionError}</p>}
                                </div>
                            </div>
                        </div>
                    )}
                </>
            ) : (
                <TrainingAdminPanel />
            )}
        </div>
    );
}
