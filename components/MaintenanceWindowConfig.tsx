import React, { useState, useEffect } from 'react';
import {
    CalendarIcon,
    ClockIcon,
    PlusIcon,
    TrashIcon,
    CheckIcon,
    AlertCircleIcon,
    RefreshCwIcon,
    ShieldCheckIcon
} from './icons';
import {
    getMaintenanceWindows,
    createMaintenanceWindow,
    deleteMaintenanceWindow,
    checkMaintenanceStatus
} from '../services/apiService';

interface MaintenanceWindow {
    id: string;
    name: string;
    start_time: string;
    end_time: string;
    recurrence: 'none' | 'daily' | 'weekly' | 'monthly';
    days_of_week: number[];
    is_active: boolean;
}

const MaintenanceWindowConfig: React.FC = () => {
    const [windows, setWindows] = useState<MaintenanceWindow[]>([]);
    const [loading, setLoading] = useState(false);
    const [isInWindow, setIsInWindow] = useState(false);
    const [showAddModal, setShowAddModal] = useState(false);

    // Form state
    const [newName, setNewName] = useState('');
    const [newStart, setNewStart] = useState('');
    const [newEnd, setNewEnd] = useState('');
    const [newRecurrence, setNewRecurrence] = useState<'none' | 'daily' | 'weekly'>('none');
    const [newDays, setNewDays] = useState<number[]>([]);

    const fetchWindows = async () => {
        setLoading(true);
        const [data, status] = await Promise.all([
            getMaintenanceWindows(),
            checkMaintenanceStatus()
        ]);
        setWindows(data);
        setIsInWindow(status.is_in_window);
        setLoading(false);
    };

    useEffect(() => {
        fetchWindows();
    }, []);

    const handleAddWindow = async () => {
        if (!newName || !newStart || !newEnd) return;

        await createMaintenanceWindow({
            tenant_id: "default",
            name: newName,
            start_time: newStart,
            end_time: newEnd,
            recurrence: newRecurrence,
            days_of_week: newDays,
            is_active: true
        });

        setShowAddModal(false);
        setNewName('');
        setNewStart('');
        setNewEnd('');
        fetchWindows();
    };

    const handleDelete = async (id: string) => {
        await deleteMaintenanceWindow(id);
        fetchWindows();
    };

    const toggleDay = (day: number) => {
        setNewDays(prev =>
            prev.includes(day) ? prev.filter(d => d !== day) : [...prev, day]
        );
    };

    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-xl font-bold text-white flex items-center gap-2">
                        <CalendarIcon className="text-blue-400" size={24} />
                        Maintenance Windows
                    </h2>
                    <p className="text-sm text-gray-400 mt-1">
                        Define scheduled windows for patch deployments and system updates.
                    </p>
                </div>
                <button
                    onClick={() => setShowAddModal(true)}
                    className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-all shadow-lg shadow-blue-500/20"
                >
                    <PlusIcon size={18} />
                    Add Window
                </button>
            </div>

            {/* Current Status Banner */}
            <div className={`p-4 rounded-xl border flex items-center justify-between ${isInWindow ? 'bg-green-500/10 border-green-500/20' : 'bg-yellow-500/10 border-yellow-500/20'}`}>
                <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-full ${isInWindow ? 'bg-green-500/20 text-green-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
                        {isInWindow ? <ShieldCheckIcon size={20} /> : <AlertCircleIcon size={20} />}
                    </div>
                    <div>
                        <div className="text-sm font-semibold text-white">
                            Current Status: {isInWindow ? 'Within Maintenance Window' : 'Outside Maintenance Window'}
                        </div>
                        <p className="text-xs text-gray-400">
                            {isInWindow
                                ? 'Deployments are currently permitted.'
                                : 'Deployments will be blocked unless maintenance window enforcement is disabled.'}
                        </p>
                    </div>
                </div>
                <button onClick={fetchWindows} className="p-2 text-gray-400 hover:text-white transition-colors">
                    <RefreshCwIcon size={18} className={loading ? 'animate-spin' : ''} />
                </button>
            </div>

            {/* Windows List */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {windows.length === 0 ? (
                    <div className="col-span-full py-12 flex flex-col items-center justify-center text-gray-500 bg-white/5 rounded-2xl border border-dashed border-white/10">
                        <CalendarIcon size={48} className="mb-4 opacity-20" />
                        <p>No maintenance windows configured</p>
                    </div>
                ) : (
                    windows.map(window => (
                        <div key={window.id} className="p-5 bg-white/5 rounded-2xl border border-white/10 hover:border-white/20 transition-all group relative">
                            <div className="flex items-start justify-between mb-4">
                                <div>
                                    <h3 className="font-semibold text-white">{window.name}</h3>
                                    <span className="text-[10px] uppercase tracking-wider font-bold text-blue-400 bg-blue-400/10 px-2 py-0.5 rounded mt-1 inline-block">
                                        {window.recurrence}
                                    </span>
                                </div>
                                <button
                                    onClick={() => handleDelete(window.id)}
                                    className="p-2 text-gray-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all"
                                >
                                    <TrashIcon size={16} />
                                </button>
                            </div>

                            <div className="space-y-2">
                                <div className="flex items-center gap-2 text-xs text-gray-400">
                                    <ClockIcon size={14} />
                                    <span>{new Date(window.start_time).toLocaleTimeString()} - {new Date(window.end_time).toLocaleTimeString()}</span>
                                </div>
                                {window.recurrence === 'weekly' && (
                                    <div className="flex gap-1 mt-2">
                                        {days.map((d, i) => (
                                            <span
                                                key={d}
                                                className={`w-6 h-6 flex items-center justify-center rounded text-[10px] font-bold ${window.days_of_week.includes(i) ? 'bg-blue-500 text-white' : 'bg-white/5 text-gray-600'}`}
                                            >
                                                {d[0]}
                                            </span>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    ))
                )}
            </div>

            {/* Add Modal */}
            {showAddModal && (
                <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
                    <div className="bg-[#121212] border border-white/10 rounded-2xl w-full max-w-md overflow-hidden shadow-2xl animate-in zoom-in-95 duration-200">
                        <div className="p-6 border-b border-white/10">
                            <h3 className="text-lg font-bold text-white">Add Maintenance Window</h3>
                        </div>

                        <div className="p-6 space-y-4">
                            <div>
                                <label className="block text-xs font-medium text-gray-400 mb-1">Window Name</label>
                                <input
                                    type="text"
                                    value={newName}
                                    onChange={e => setNewName(e.target.value)}
                                    placeholder="e.g. Weekly Production Patching"
                                    className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                                />
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-medium text-gray-400 mb-1">Start Time</label>
                                    <input
                                        type="datetime-local"
                                        value={newStart}
                                        onChange={e => setNewStart(e.target.value)}
                                        className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-medium text-gray-400 mb-1">End Time</label>
                                    <input
                                        type="datetime-local"
                                        value={newEnd}
                                        onChange={e => setNewEnd(e.target.value)}
                                        className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="block text-xs font-medium text-gray-400 mb-1">Recurrence</label>
                                <select
                                    value={newRecurrence}
                                    onChange={e => setNewRecurrence(e.target.value as any)}
                                    className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                                >
                                    <option value="none">One-time</option>
                                    <option value="daily">Daily</option>
                                    <option value="weekly">Weekly</option>
                                </select>
                            </div>

                            {newRecurrence === 'weekly' && (
                                <div>
                                    <label className="block text-xs font-medium text-gray-400 mb-1">Days of Week</label>
                                    <div className="flex justify-between">
                                        {days.map((d, i) => (
                                            <button
                                                key={d}
                                                onClick={() => toggleDay(i)}
                                                className={`w-10 h-10 rounded-lg flex items-center justify-center text-xs font-bold transition-all ${newDays.includes(i) ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20' : 'bg-white/5 text-gray-500 hover:bg-white/10'}`}
                                            >
                                                {d[0]}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>

                        <div className="p-6 bg-white/5 flex gap-3">
                            <button
                                onClick={() => setShowAddModal(false)}
                                className="flex-1 px-4 py-2 bg-white/5 hover:bg-white/10 text-white rounded-lg transition-all"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleAddWindow}
                                className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-all"
                            >
                                Create Window
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default MaintenanceWindowConfig;
