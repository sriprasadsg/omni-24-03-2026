import React, { useState, useEffect } from 'react';
import { authFetch, API_BASE } from '../services/apiService';
import { 
    Target, 
    Zap, 
    CheckCircle2, 
    Circle, 
    Clock, 
    Plus, 
    Search, 
    MoreVertical, 
    ArrowRight,
    Loader2,
    ShieldCheck,
    Cpu,
    BarChart3
} from 'lucide-react';

interface GoalTask {
    task_id: string;
    description: string;
    capability: string;
    status: 'pending' | 'completed' | 'in_progress';
    estimated_minutes: number;
    order: number;
}

interface Goal {
    id: string;
    objective: string;
    priority: number;
    category: string;
    status: 'active' | 'pending_approval' | 'completed' | 'rejected';
    deadline: string | null;
    tasks: GoalTask[];
    progress_pct: number;
    completed_tasks: number;
    total_tasks: number;
}

export const GoalSystemDashboard: React.FC = () => {
    const [goals, setGoals] = useState<Goal[]>([]);
    const [loading, setLoading] = useState(true);
    const [activeGoal, setActiveGoal] = useState<Goal | null>(null);
    const [showNewGoal, setShowNewGoal] = useState(false);
    const [newGoalObjective, setNewGoalObjective] = useState('');

    const fetchGoals = async () => {
        setLoading(true);
        try {
            const res = await authFetch(`${API_BASE}/goals`);
            const data = await res.json();
            setGoals(data.goals || []);
            if (!activeGoal && data.goals && data.goals.length > 0) {
                setActiveGoal(data.goals[0]);
            }
        } catch (error) {
            console.error('Error fetching goals:', error);
        }
        setLoading(false);
    };

    useEffect(() => {
        fetchGoals();
    }, []);

    const createGoal = async () => {
        if (!newGoalObjective) return;
        setLoading(true);
        try {
            const res = await authFetch(`${API_BASE}/goals`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ objective: newGoalObjective, auto_approve: true })
            });
            const newGoal = await res.json();
            setGoals([newGoal, ...goals]);
            setActiveGoal(newGoal);
            setNewGoalObjective('');
            setShowNewGoal(false);
        } catch (error) {
            console.error('Error creating goal:', error);
        }
        setLoading(false);
    };

    const completeTask = async (goalId: string, taskId: string) => {
        try {
            const res = await authFetch(`${API_BASE}/goals/${goalId}/tasks/${taskId}/complete`, { method: 'POST' });
            const data = await res.json();
            
            // Update local state
            const updatedGoals = goals.map(g => {
                if (g.id === goalId) {
                    const updatedTasks = g.tasks.map(t => t.task_id === taskId ? { ...t, status: 'completed' } : t);
                    return { ...g, tasks: updatedTasks as GoalTask[], progress_pct: data.progress_pct, status: data.goal_status };
                }
                return g;
            });
            setGoals(updatedGoals);
            if (activeGoal?.id === goalId) {
                setActiveGoal(updatedGoals.find(g => g.id === goalId) || null);
            }
        } catch (error) {
            console.error('Error completing task:', error);
        }
    };

    const getPriorityColor = (prio: number) => {
        if (prio <= 2) return 'bg-red-500';
        if (prio <= 5) return 'bg-amber-500';
        return 'bg-blue-500';
    };

    return (
        <div className="flex h-screen bg-slate-50 dark:bg-slate-900 overflow-hidden">
            {/* Sidebar - Goal List */}
            <div className="w-96 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col">
                <div className="p-6 border-b border-slate-100 dark:border-slate-800">
                    <div className="flex justify-between items-center mb-6">
                        <h1 className="text-xl font-bold text-slate-900 dark:text-white flex items-center">
                            <Target className="w-5 h-5 mr-2 text-indigo-500" />
                            Autonomous Goals
                        </h1>
                        <button 
                            onClick={() => setShowNewGoal(true)}
                            className="p-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
                        >
                            <Plus className="w-5 h-5" />
                        </button>
                    </div>
                    <div className="relative">
                        <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
                        <input 
                            type="text" 
                            placeholder="Search goals..." 
                            className="w-full pl-10 pr-4 py-2 bg-slate-50 dark:bg-slate-800 border-none rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"
                        />
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto p-4 space-y-3">
                    {goals.map(goal => (
                        <div 
                            key={goal.id}
                            onClick={() => setActiveGoal(goal)}
                            className={`p-4 rounded-xl border cursor-pointer transition-all ${activeGoal?.id === goal.id ? 'bg-indigo-50 dark:bg-indigo-900/20 border-indigo-200 dark:border-indigo-500/30' : 'bg-white dark:bg-slate-800 border-slate-100 dark:border-slate-800 hover:border-slate-200'}`}
                        >
                            <div className="flex justify-between items-start mb-2">
                                <span className={`px-2 py-0.5 rounded-[4px] text-[10px] font-bold text-white uppercase ${getPriorityColor(goal.priority)}`}>
                                    P{goal.priority}
                                </span>
                                <span className="text-[10px] text-slate-400 uppercase font-bold">{goal.category}</span>
                            </div>
                            <h3 className="text-sm font-bold text-slate-900 dark:text-white line-clamp-2 mb-3">{goal.objective}</h3>
                            <div className="flex items-center justify-between">
                                <div className="flex-1 mr-4">
                                    <div className="w-full bg-slate-100 dark:bg-slate-700 rounded-full h-1.5">
                                        <div className="bg-indigo-500 h-1.5 rounded-full" style={{ width: `${goal.progress_pct}%` }}></div>
                                    </div>
                                </div>
                                <span className="text-xs font-bold text-slate-500">{Math.round(goal.progress_pct)}%</span>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Main Content - Goal Detail & Task Plan */}
            <div className="flex-1 flex flex-col overflow-hidden">
                {activeGoal ? (
                    <>
                        <div className="p-8 bg-white dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
                            <div className="flex justify-between items-start mb-6">
                                <div className="max-w-2xl">
                                    <div className="flex items-center space-x-3 mb-2">
                                        <span className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider text-white ${getPriorityColor(activeGoal.priority)}`}>
                                            Priority {activeGoal.priority}
                                        </span>
                                        <span className="text-sm text-slate-400">Category: <span className="text-slate-900 dark:text-slate-200 font-bold uppercase">{activeGoal.category}</span></span>
                                    </div>
                                    <h2 className="text-3xl font-bold text-slate-900 dark:text-white leading-tight">{activeGoal.objective}</h2>
                                </div>
                                <div className="flex space-x-2">
                                    <button className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg text-slate-500">
                                        <BarChart3 className="w-5 h-5" />
                                    </button>
                                    <button className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg text-slate-500">
                                        <MoreVertical className="w-5 h-5" />
                                    </button>
                                </div>
                            </div>

                            <div className="grid grid-cols-4 gap-6">
                                <div className="p-4 bg-slate-50 dark:bg-slate-800/50 rounded-xl">
                                    <p className="text-xs text-slate-400 font-bold uppercase mb-1">Status</p>
                                    <p className="text-lg font-bold text-slate-900 dark:text-white flex items-center capitalize">
                                        <Zap className="w-4 h-4 mr-2 text-amber-500" />
                                        {activeGoal.status.replace('_', ' ')}
                                    </p>
                                </div>
                                <div className="p-4 bg-slate-50 dark:bg-slate-800/50 rounded-xl">
                                    <p className="text-xs text-slate-400 font-bold uppercase mb-1">Progress</p>
                                    <p className="text-lg font-bold text-slate-900 dark:text-white">{Math.round(activeGoal.progress_pct)}% Complete</p>
                                </div>
                                <div className="p-4 bg-slate-50 dark:bg-slate-800/50 rounded-xl">
                                    <p className="text-xs text-slate-400 font-bold uppercase mb-1">Tasks</p>
                                    <p className="text-lg font-bold text-slate-900 dark:text-white">{activeGoal.completed_tasks} / {activeGoal.total_tasks}</p>
                                </div>
                                <div className="p-4 bg-slate-50 dark:bg-slate-800/50 rounded-xl">
                                    <p className="text-xs text-slate-400 font-bold uppercase mb-1">Deadline</p>
                                    <p className="text-lg font-bold text-slate-900 dark:text-white flex items-center">
                                        <Clock className="w-4 h-4 mr-2 text-slate-400" />
                                        {activeGoal.deadline ? new Date(activeGoal.deadline).toLocaleDateString() : 'None'}
                                    </p>
                                </div>
                            </div>
                        </div>

                        <div className="flex-1 overflow-y-auto p-8 bg-slate-50 dark:bg-slate-900">
                            <div className="max-w-4xl mx-auto space-y-6">
                                <div className="flex items-center justify-between">
                                    <h3 className="text-xl font-bold text-slate-900 dark:text-white flex items-center">
                                        <ShieldCheck className="w-6 h-6 mr-2 text-indigo-500" />
                                        Autonomous Decomposed Plan
                                    </h3>
                                    <span className="text-sm text-slate-500">LLM Generation v2.4 (Ollama/Llama3)</span>
                                </div>

                                <div className="space-y-4">
                                    {activeGoal.tasks.sort((a, b) => a.order - b.order).map((task, idx) => (
                                        <div 
                                            key={task.task_id}
                                            className={`p-6 rounded-2xl border bg-white dark:bg-slate-800 transition-all flex items-start group ${task.status === 'completed' ? 'border-emerald-100 dark:border-emerald-900/30' : 'border-slate-100 dark:border-slate-800 shadow-sm'}`}
                                        >
                                            <div className="mr-4 mt-1">
                                                {task.status === 'completed' ? (
                                                    <CheckCircle2 className="w-6 h-6 text-emerald-500" />
                                                ) : (
                                                    <button 
                                                        onClick={() => completeTask(activeGoal.id, task.task_id)}
                                                        className="w-6 h-6 rounded-full border-2 border-slate-200 dark:border-slate-700 hover:border-indigo-500 transition-colors flex items-center justify-center group-hover:bg-indigo-50 dark:group-hover:bg-indigo-900/30"
                                                    >
                                                        <div className="w-2 h-2 bg-indigo-500 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"></div>
                                                    </button>
                                                )}
                                            </div>
                                            <div className="flex-1">
                                                <div className="flex justify-between items-start mb-2">
                                                    <h4 className={`font-bold text-lg ${task.status === 'completed' ? 'text-slate-400 line-through' : 'text-slate-900 dark:text-white'}`}>
                                                        {task.description}
                                                    </h4>
                                                    <span className="text-xs px-2 py-1 bg-slate-100 dark:bg-slate-700 rounded text-slate-500 font-mono">
                                                        {task.capability}
                                                    </span>
                                                </div>
                                                <div className="flex items-center space-x-4 text-sm">
                                                    <span className="text-slate-400 flex items-center">
                                                        <Clock className="w-4 h-4 mr-1" />
                                                        {task.estimated_minutes} min
                                                    </span>
                                                    <span className="text-slate-400 flex items-center">
                                                        <Cpu className="w-4 h-4 mr-1" />
                                                        Automated Execution
                                                    </span>
                                                </div>
                                            </div>
                                            {task.status !== 'completed' && (
                                                <button className="ml-4 p-2 bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity flex items-center">
                                                    Run Now
                                                    <ArrowRight className="w-4 h-4 ml-1" />
                                                </button>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </>
                ) : (
                    <div className="flex-1 flex flex-col items-center justify-center text-slate-400">
                        <Target className="w-16 h-16 mb-4 opacity-10" />
                        <p className="text-lg">Select a goal to view the decomposed task plan</p>
                    </div>
                )}
            </div>

            {/* New Goal Modal */}
            {showNewGoal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-slate-900/50 backdrop-blur-sm">
                    <div className="bg-white dark:bg-slate-900 w-full max-w-lg rounded-2xl shadow-2xl overflow-hidden border border-slate-200 dark:border-slate-800">
                        <div className="p-8">
                            <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-6">Create New Autonomous Goal</h2>
                            <div className="space-y-6">
                                <div>
                                    <label className="block text-sm font-bold text-slate-400 uppercase mb-2">Objective (Natural Language)</label>
                                    <textarea 
                                        value={newGoalObjective}
                                        onChange={(e) => setNewGoalObjective(e.target.value)}
                                        rows={3}
                                        placeholder="e.g. Reduce cloud attack surface by remediating open security groups..."
                                        className="w-full p-4 bg-slate-50 dark:bg-slate-800 border-none rounded-xl text-slate-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                                    ></textarea>
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-sm font-bold text-slate-400 uppercase mb-2">Priority</label>
                                        <select className="w-full p-3 bg-slate-50 dark:bg-slate-800 border-none rounded-xl text-slate-900 dark:text-white">
                                            <option value="1">P1 - Critical</option>
                                            <option value="2">P2 - High</option>
                                            <option value="5" selected>P5 - Standard</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-bold text-slate-400 uppercase mb-2">Category</label>
                                        <select className="w-full p-3 bg-slate-50 dark:bg-slate-800 border-none rounded-xl text-slate-900 dark:text-white">
                                            <option value="security">Security</option>
                                            <option value="compliance">Compliance</option>
                                            <option value="cost">Cost Optimization</option>
                                        </select>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div className="p-6 bg-slate-50 dark:bg-slate-800/50 flex justify-end space-x-4">
                            <button 
                                onClick={() => setShowNewGoal(false)}
                                className="px-6 py-2 text-slate-500 font-bold hover:text-slate-900 transition-colors"
                            >
                                Cancel
                            </button>
                            <button 
                                onClick={createGoal}
                                disabled={loading || !newGoalObjective}
                                className="px-8 py-2 bg-indigo-600 text-white rounded-xl font-bold flex items-center hover:bg-indigo-700 disabled:opacity-50 transition-all shadow-lg shadow-indigo-600/20"
                            >
                                {loading ? <Loader2 className="w-5 h-5 animate-spin mr-2" /> : <Zap className="w-5 h-5 mr-2" />}
                                Decompose & Start
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
