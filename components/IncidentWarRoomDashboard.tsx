import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';
import { ShieldAlertIcon, ClockIcon, UsersIcon, MessageSquareIcon, FileTextIcon, ActivityIcon, PlusIcon } from './icons';
import { showToast } from '../utils/toast';

interface Incident {
    id: string;
    incident_number: string;
    title: string;
    severity: string;
    status: string;
    description: string;
    assigned_to: string | null;
    created_at: string;
    updated_at: string;
    contained_at: string | null;
    eradicated_at: string | null;
    resolved_at: string | null;
    closed_at: string | null;
    mttr_minutes: number | null;
    tags: string[];
    timeline: { timestamp: string; actor: string; event: string; detail?: string }[];
    tasks: { id: string; title: string; assignee: string; status: string; priority: string }[];
    chat: { timestamp: string; user: string; message: string }[];
}

interface Summary {
    total: number;
    open: number;
    by_severity: Record<string, number>;
    by_status: Record<string, number>;
    avg_mttr_minutes: number | null;
}

const SEV_COLORS: Record<string, string> = {
    P1: 'bg-red-600 text-white shadow-lg shadow-red-600/20 border-red-500',
    P2: 'bg-orange-500 text-white shadow-lg shadow-orange-500/20 border-orange-400',
    P3: 'bg-amber-500 text-white shadow-lg shadow-amber-500/20 border-amber-400',
    P4: 'bg-slate-600 text-white border-slate-500',
};

const STATUS_COLORS: Record<string, string> = {
    open: 'text-red-500',
    investigating: 'text-amber-500',
    contained: 'text-blue-500',
    eradicated: 'text-indigo-500',
    resolved: 'text-emerald-500',
    closed: 'text-slate-500',
};

const IncidentWarRoomDashboard: React.FC = () => {
    const [incidents, setIncidents] = useState<Incident[]>([]);
    const [summary, setSummary] = useState<Summary | null>(null);
    const [selected, setSelected] = useState<Incident | null>(null);
    const [activeTab, setActiveTab] = useState<'timeline' | 'tasks' | 'chat' | 'evidence'>('timeline');
    const [showCreate, setShowCreate] = useState(false);
    const [form, setForm] = useState({ title: '', severity: 'P2', description: '' });
    const [saving, setSaving] = useState(false);
    const [chatMsg, setChatMsg] = useState('');
    const [taskForm, setTaskForm] = useState({ title: '', assignee: '', priority: 'medium' });
    const [tlEvent, setTlEvent] = useState('');
    const [enriching, setEnriching] = useState(false);

    useEffect(() => { loadAll(); }, []);

    // Poll selected incident every 5 s so collaborators' chat/timeline updates appear live
    useEffect(() => {
        if (!selected?.id) return;
        const id = selected.id;
        const timer = setInterval(() => { loadIncident(id); }, 5000);
        return () => clearInterval(timer);
    }, [selected?.id]);

    async function loadAll() {
        try {
            const [iRes, sRes] = await Promise.all([
                authFetch('/api/incidents'),
                authFetch('/api/incidents/summary'),
            ]);
            const i = await iRes.json();
            const s = await sRes.json();
            setIncidents(i.incidents || []);
            setSummary(s);
            if (i.incidents && i.incidents.length > 0) {
                // Functional update: only auto-select if nothing is already selected.
                // Avoids stale-closure bug — reads current state at update time.
                setSelected(prev => prev ?? i.incidents[0]);
            }
        } catch (e) { console.error(e); }
    }

    async function loadIncident(id: string) {
        try {
            const r = await authFetch(`/api/incidents/${id}`);
            if (!r.ok) return;
            const d = await r.json();
            setSelected(d);
        } catch (e) {
            console.error('Failed to refresh incident:', e);
        }
    }

    async function createIncident() {
        setSaving(true);
        try {
            const r = await authFetch('/api/incidents', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(form),
            });
            if (r.ok) { loadAll(); setShowCreate(false); setForm({ title: '', severity: 'P2', description: '' }); }
        } finally { setSaving(false); }
    }

    async function updateStatus(id: string, status: string) {
        await authFetch(`/api/incidents/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status }),
        });
        loadIncident(id);
        loadAll();
    }

    async function addTimelineEvent(id: string, event: string) {
        if (!event.trim()) return;
        await authFetch(`/api/incidents/${id}/timeline`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ event, detail: '' }),
        });
        loadIncident(id);
    }

    async function enrichFromCorrelations(id: string) {
        setEnriching(true);
        try {
            const r = await authFetch('/api/correlations?limit=5&severity=High');
            if (!r.ok) return;
            const correlations: any[] = await r.json();
            if (!correlations.length) {
                showToast('No recent high-severity correlations found to enrich this timeline.', 'info');
                return;
            }
            for (const corr of correlations) {
                const eventLabel = corr.pattern_name || corr.rule_name || 'Correlation Match';
                const detail = `[AUTO] ${eventLabel} — ${corr.event_count ?? ''} events, confidence ${Math.round((corr.confidence ?? 0) * 100)}%`;
                await authFetch(`/api/incidents/${id}/timeline`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ event: 'CORRELATED THREAT DETECTED', detail }),
                });
            }
            await loadIncident(id);
        } finally {
            setEnriching(false);
        }
    }

    async function sendChat(id: string) {
        if (!chatMsg.trim()) return;
        await authFetch(`/api/incidents/${id}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: chatMsg }),
        });
        setChatMsg('');
        loadIncident(id);
    }

    return (
        <div className="p-6 bg-slate-950 min-h-screen text-slate-100 font-sans selection:bg-red-500/30">
            {/* Top Bar */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 mb-8">
                <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-2xl bg-red-600/20 border border-red-500/40 flex items-center justify-center text-red-500 animate-pulse">
                        <ShieldAlertIcon size={28} />
                    </div>
                    <div>
                        <h1 className="text-3xl font-black tracking-tighter text-white uppercase italic">Incident War Room</h1>
                        <div className="flex items-center gap-2 mt-1">
                            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping"></span>
                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Active Crisis Mode • Tactical Command Center</p>
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    <div className="hidden md:flex -space-x-2 mr-4">
                        {[1, 2, 3].map(i => (
                            <div key={i} className="w-8 h-8 rounded-full border-2 border-slate-950 bg-slate-800 flex items-center justify-center text-[10px] font-bold text-slate-400">
                                {String.fromCharCode(64 + i)}
                            </div>
                        ))}
                        <div className="w-8 h-8 rounded-full border-2 border-slate-950 bg-indigo-600 flex items-center justify-center text-[10px] font-bold text-white">
                            +4
                        </div>
                    </div>
                    <button 
                        onClick={() => setShowCreate(true)}
                        className="bg-red-600 hover:bg-red-500 text-white px-6 py-3 rounded-xl font-black text-sm transition-all shadow-xl shadow-red-600/30 flex items-center gap-2"
                    >
                        <PlusIcon size={18} /> DECLARE INCIDENT
                    </button>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Sidebar: Incident List */}
                <div className="lg:col-span-3 space-y-4">
                    <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-4">
                        <h2 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-4 flex items-center justify-between">
                            Active Feed
                            <span className="bg-red-600 text-white px-2 py-0.5 rounded text-[8px]">{incidents.length}</span>
                        </h2>
                        <div className="space-y-2 max-h-[calc(100vh-280px)] overflow-y-auto pr-2 custom-scrollbar">
                            {incidents.map(inc => (
                                <div key={inc.id}
                                    onClick={() => { setSelected(inc); loadIncident(inc.id); }}
                                    className={`group p-4 rounded-xl border transition-all cursor-pointer ${
                                        selected?.id === inc.id 
                                        ? 'bg-slate-800 border-red-500/50 shadow-lg shadow-red-500/5' 
                                        : 'bg-slate-900/40 border-slate-800 hover:border-slate-700'
                                    }`}>
                                    <div className="flex justify-between items-start mb-2">
                                        <span className={`text-[9px] px-2 py-0.5 rounded font-black tracking-tighter ${SEV_COLORS[inc.severity]}`}>
                                            {inc.severity}
                                        </span>
                                        <span className="text-[9px] font-mono text-slate-500">{inc.incident_number}</span>
                                    </div>
                                    <h3 className={`text-sm font-bold leading-tight ${selected?.id === inc.id ? 'text-white' : 'text-slate-300'}`}>
                                        {inc.title}
                                    </h3>
                                    <div className="flex items-center gap-2 mt-3">
                                        <span className={`w-1.5 h-1.5 rounded-full ${STATUS_COLORS[inc.status] || 'bg-slate-500'} bg-current`}></span>
                                        <span className={`text-[10px] font-bold uppercase tracking-tighter ${STATUS_COLORS[inc.status] || 'text-slate-500'}`}>
                                            {inc.status}
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                {/* Main Command Area */}
                <div className="lg:col-span-9">
                    {selected ? (
                        <div className="space-y-6">
                            {/* Incident Header & Meta */}
                            <div className="bg-slate-900 rounded-3xl border border-slate-800 overflow-hidden shadow-2xl">
                                <div className="p-8 bg-gradient-to-br from-slate-900 to-slate-950 border-b border-slate-800">
                                    <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                                        <div className="flex-1">
                                            <div className="flex items-center gap-3 mb-4">
                                                <span className={`px-4 py-1.5 rounded-full text-xs font-black tracking-widest ${SEV_COLORS[selected.severity]}`}>
                                                    SEVERITY {selected.severity}
                                                </span>
                                                <span className="text-slate-500 font-mono text-sm">{selected.incident_number}</span>
                                                <span className="text-slate-500 text-xs flex items-center gap-1">
                                                    <ClockIcon size={12} /> {new Date(selected.created_at).toLocaleString()}
                                                </span>
                                            </div>
                                            <h2 className="text-4xl font-black text-white tracking-tighter mb-4 leading-none uppercase italic">
                                                {selected.title}
                                            </h2>
                                            <p className="text-slate-400 text-sm max-w-3xl leading-relaxed">
                                                {selected.description}
                                            </p>
                                        </div>
                                        <div className="bg-slate-950/50 p-4 rounded-2xl border border-slate-800 w-full md:w-64">
                                            <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">Lifecycle Control</p>
                                            <div className="grid grid-cols-2 gap-2">
                                                {['open', 'investigating', 'contained', 'resolved'].map(s => (
                                                    <button key={s}
                                                        onClick={() => updateStatus(selected.id, s)}
                                                        className={`text-[9px] font-black uppercase tracking-widest py-2 rounded-lg border transition-all ${
                                                            selected.status === s 
                                                            ? 'bg-red-600 border-red-500 text-white' 
                                                            : 'bg-slate-900 border-slate-800 text-slate-500 hover:text-slate-300'
                                                        }`}>
                                                        {s}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* Tabs & Workspace */}
                                <div className="flex bg-slate-900/50 border-b border-slate-800 px-4">
                                    {[
                                        { id: 'timeline', label: 'Timeline', icon: ActivityIcon },
                                        { id: 'tasks', label: 'Action Items', icon: FileTextIcon },
                                        { id: 'chat', label: 'Communications', icon: MessageSquareIcon },
                                        { id: 'evidence', label: 'Evidence Locker', icon: ShieldAlertIcon }
                                    ].map(tab => (
                                        <button key={tab.id} onClick={() => setActiveTab(tab.id as any)}
                                            className={`flex items-center gap-2 px-6 py-4 text-xs font-black uppercase tracking-widest transition-all border-b-2 ${
                                                activeTab === tab.id 
                                                ? 'text-red-500 border-red-500 bg-red-500/5' 
                                                : 'text-slate-500 border-transparent hover:text-slate-300'
                                            }`}>
                                            <tab.icon size={14} />
                                            {tab.label}
                                        </button>
                                    ))}
                                </div>

                                <div className="p-8 min-h-[400px]">
                                    {activeTab === 'timeline' && (
                                        <div className="space-y-6 relative before:absolute before:left-[11px] before:top-2 before:bottom-2 before:w-px before:bg-slate-800">
                                            {selected.timeline.map((e, i) => (
                                                <div key={i} className="flex gap-6 relative group">
                                                    <div className="w-6 h-6 rounded-full bg-slate-950 border border-slate-800 flex items-center justify-center relative z-10 group-hover:border-red-500 transition-colors">
                                                        <div className="w-2 h-2 rounded-full bg-slate-700 group-hover:bg-red-500 transition-colors"></div>
                                                    </div>
                                                    <div className="flex-1">
                                                        <div className="flex items-center gap-3 mb-1">
                                                            <span className="text-white font-bold text-sm uppercase italic">{e.event}</span>
                                                            <span className="text-[10px] text-slate-500 font-mono">{new Date(e.timestamp).toLocaleTimeString()}</span>
                                                        </div>
                                                        {e.detail && <p className="text-slate-400 text-xs leading-relaxed mb-1">{e.detail}</p>}
                                                        <div className="flex items-center gap-2">
                                                            <UsersIcon size={10} className="text-slate-600" />
                                                            <span className="text-[10px] text-slate-500 font-bold uppercase">{e.actor}</span>
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                            <div className="flex gap-4 mt-8 bg-slate-950/50 p-4 rounded-2xl border border-slate-800">
                                                <input value={tlEvent} onChange={e => setTlEvent(e.target.value)}
                                                    onKeyDown={e => { if (e.key === 'Enter' && tlEvent.trim()) { addTimelineEvent(selected.id, tlEvent); setTlEvent(''); }}}
                                                    placeholder="Add tactical milestone..."
                                                    className="flex-1 bg-transparent border-none text-sm text-white placeholder-slate-600 focus:ring-0" />
                                                <button onClick={() => { if (tlEvent.trim()) { addTimelineEvent(selected.id, tlEvent); setTlEvent(''); } }}
                                                    className="bg-slate-800 hover:bg-slate-700 px-6 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all">
                                                    POST MILESTONE
                                                </button>
                                                <button onClick={() => enrichFromCorrelations(selected.id)}
                                                    disabled={enriching}
                                                    title="Auto-add recent high-severity SIEM correlations to this timeline"
                                                    className="bg-red-900/40 hover:bg-red-900/70 border border-red-700/50 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest text-red-300 transition-all disabled:opacity-50 flex items-center gap-1">
                                                    {enriching ? '⏳' : '⚡'} ENRICH
                                                </button>
                                            </div>
                                        </div>
                                    )}

                                    {activeTab === 'tasks' && (
                                        <div className="space-y-4">
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                {selected.tasks.map(t => (
                                                    <div key={t.id} className="bg-slate-950/50 border border-slate-800 rounded-2xl p-4 flex items-center gap-4 group hover:border-slate-700 transition-all">
                                                        <button className={`w-6 h-6 rounded-lg border flex items-center justify-center transition-all ${
                                                            t.status === 'done' ? 'bg-emerald-600 border-emerald-500 text-white' : 'border-slate-700 hover:border-slate-500'
                                                        }`}>
                                                            {t.status === 'done' && <ActivityIcon size={14} />}
                                                        </button>
                                                        <div className="flex-1">
                                                            <p className={`text-sm font-bold ${t.status === 'done' ? 'text-slate-500 line-through' : 'text-slate-200'}`}>{t.title}</p>
                                                            <div className="flex items-center gap-2 mt-1">
                                                                <span className="text-[9px] font-black uppercase text-slate-500">{t.assignee}</span>
                                                                <span className={`text-[8px] font-black uppercase px-1.5 rounded border ${
                                                                    t.priority === 'high' ? 'text-red-500 border-red-500/30' : 'text-slate-500 border-slate-800'
                                                                }`}>{t.priority}</span>
                                                            </div>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                            <div className="mt-8 bg-slate-950/50 p-6 rounded-2xl border border-slate-800 border-dashed">
                                                <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-4">Assign New Task</p>
                                                <div className="flex flex-col md:flex-row gap-3">
                                                    <input placeholder="Task definition..." className="flex-1 bg-slate-900 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:border-red-500 transition-all" />
                                                    <input placeholder="Assignee" className="md:w-48 bg-slate-900 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:border-red-500 transition-all" />
                                                    <button className="bg-white text-slate-950 px-6 py-3 rounded-xl font-black text-[10px] uppercase tracking-widest hover:bg-slate-200 transition-all">CREATE TASK</button>
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    {activeTab === 'chat' && (
                                        <div className="flex flex-col h-[400px]">
                                            <div className="flex-1 space-y-4 overflow-y-auto pr-4 custom-scrollbar mb-4">
                                                {selected.chat.map((m, i) => (
                                                    <div key={i} className="flex flex-col items-start max-w-[80%]">
                                                        <div className="flex items-center gap-2 mb-1">
                                                            <span className="text-[10px] font-black text-red-500 uppercase tracking-widest">{m.user}</span>
                                                            <span className="text-[9px] text-slate-600 font-mono">{new Date(m.timestamp).toLocaleTimeString()}</span>
                                                        </div>
                                                        <div className="bg-slate-950 border border-slate-800 p-4 rounded-2xl rounded-tl-none">
                                                            <p className="text-sm text-slate-300 leading-relaxed">{m.message}</p>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                            <div className="relative">
                                                <input value={chatMsg} onChange={e => setChatMsg(e.target.value)}
                                                    onKeyDown={e => e.key === 'Enter' && sendChat(selected.id)}
                                                    placeholder="Operational comms secure..."
                                                    className="w-full bg-slate-950 border border-slate-800 rounded-2xl px-6 py-4 text-sm focus:border-red-500 transition-all pr-32" />
                                                <button onClick={() => sendChat(selected.id)} className="absolute right-3 top-2 bottom-2 px-6 bg-red-600 text-white rounded-xl font-black text-[10px] uppercase tracking-widest hover:bg-red-500 transition-all">SEND</button>
                                            </div>
                                        </div>
                                    )}

                                    {activeTab === 'evidence' && (
                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                            {[
                                                { type: 'Log File', name: 'process_tree_dump.json', size: '2.4MB' },
                                                { type: 'Screenshot', name: 'suspicious_powershell.png', size: '840KB' },
                                                { type: 'Memory Dump', name: 'lsass_mem_sector.dmp', size: '124MB' },
                                                { type: 'Network PCAP', name: 'exfil_stream_443.pcap', size: '18MB' }
                                            ].map((file, i) => (
                                                <div key={i} className="bg-slate-950 border border-slate-800 rounded-2xl p-4 group hover:border-red-500/50 transition-all cursor-pointer">
                                                    <div className="aspect-square bg-slate-900 rounded-xl mb-4 flex items-center justify-center text-slate-700 group-hover:text-red-500/40 transition-colors">
                                                        <FileTextIcon size={48} />
                                                    </div>
                                                    <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1">{file.type}</p>
                                                    <p className="text-xs font-bold text-white truncate">{file.name}</p>
                                                    <p className="text-[9px] text-slate-600 mt-2">{file.size}</p>
                                                </div>
                                            ))}
                                            <div className="border-2 border-dashed border-slate-800 rounded-2xl flex flex-col items-center justify-center p-4 hover:border-red-500/30 transition-all cursor-pointer">
                                                <PlusIcon size={24} className="text-slate-700 mb-2" />
                                                <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest text-center">Upload Evidence</p>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Tactical HUD */}
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                <div className="bg-slate-900/50 border border-slate-800 rounded-3xl p-6">
                                    <h3 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-4">Threat Origin</h3>
                                    <div className="flex items-center gap-4">
                                        <div className="w-10 h-10 rounded-full bg-red-600/10 flex items-center justify-center text-red-500">RU</div>
                                        <div>
                                            <p className="text-sm font-black">Moscow, Russia</p>
                                            <p className="text-[10px] text-slate-500">IP: 92.14.88.102 (VPN)</p>
                                        </div>
                                    </div>
                                </div>
                                <div className="bg-slate-900/50 border border-slate-800 rounded-3xl p-6">
                                    <h3 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-4">Containment Delta</h3>
                                    <div className="flex items-center gap-4">
                                        <div className="w-10 h-10 rounded-full bg-indigo-600/10 flex items-center justify-center text-indigo-500 font-black">42m</div>
                                        <div>
                                            <p className="text-sm font-black">Time to Contain</p>
                                            <p className="text-[10px] text-slate-500">Below organizational SLA</p>
                                        </div>
                                    </div>
                                </div>
                                <div className="bg-slate-900/50 border border-slate-800 rounded-3xl p-6">
                                    <h3 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-4">Team Presence</h3>
                                    <div className="flex -space-x-2">
                                        {[1, 2, 3, 4, 5].map(i => (
                                            <div key={i} className="w-10 h-10 rounded-full border-4 border-slate-900 bg-slate-800 flex items-center justify-center text-[10px] font-black">
                                                U{i}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="h-full flex flex-col items-center justify-center text-center p-12 bg-slate-900/20 border border-slate-800 border-dashed rounded-3xl">
                            <ShieldAlertIcon size={64} className="text-slate-800 mb-6" />
                            <h2 className="text-2xl font-black text-slate-700 uppercase italic">Select an incident to enter War Room</h2>
                            <p className="text-slate-600 max-w-sm mt-2 text-sm">Real-time collaboration and tactical response modules will activate upon selection.</p>
                        </div>
                    )}
                </div>
            </div>

            {/* Declare Incident Modal */}
            {showCreate && (
                <div className="fixed inset-0 bg-slate-950/90 backdrop-blur-md flex items-center justify-center z-50 p-4">
                    <div className="bg-slate-900 rounded-3xl w-full max-w-lg border border-slate-800 shadow-2xl overflow-hidden">
                        <div className="p-8">
                            <div className="flex justify-between items-center mb-8">
                                <h3 className="font-black text-2xl uppercase italic text-white tracking-tighter">Declare Critical Incident</h3>
                                <button onClick={() => setShowCreate(false)} className="text-slate-500 hover:text-white transition-colors">
                                    <PlusIcon size={24} className="rotate-45" />
                                </button>
                            </div>
                            <div className="space-y-6">
                                <div>
                                    <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest block mb-2">Primary Title</label>
                                    <input value={form.title} onChange={e => setForm(p => ({ ...p, title: e.target.value }))}
                                        placeholder="Identify the threat vector..."
                                        className="w-full bg-slate-950 border border-slate-800 rounded-2xl px-6 py-4 text-sm text-white focus:border-red-500 transition-all" />
                                </div>
                                <div>
                                    <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest block mb-2">Priority Tier</label>
                                    <div className="grid grid-cols-4 gap-3">
                                        {['P1', 'P2', 'P3', 'P4'].map(s => (
                                            <button key={s}
                                                onClick={() => setForm(p => ({ ...p, severity: s }))}
                                                className={`flex items-center justify-center py-3 rounded-xl border text-xs font-black transition-all ${
                                                    form.severity === s 
                                                    ? 'bg-red-600 border-red-500 text-white shadow-lg shadow-red-600/20' 
                                                    : 'bg-slate-950 border-slate-800 text-slate-500 hover:border-slate-700'
                                                }`}>
                                                {s}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                                <div>
                                    <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest block mb-2">Tactical Summary</label>
                                    <textarea value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))}
                                        rows={4} placeholder="Initial assessment, observable IOCs, and affected assets..."
                                        className="w-full bg-slate-950 border border-slate-800 rounded-2xl px-6 py-4 text-sm text-white focus:border-red-500 transition-all resize-none" />
                                </div>
                                <div className="flex gap-4 pt-4">
                                    <button onClick={createIncident} disabled={saving || !form.title}
                                        className="flex-1 bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white px-8 py-4 rounded-2xl font-black text-[11px] uppercase tracking-widest transition-all shadow-xl shadow-red-600/30">
                                        {saving ? 'COMMITTING...' : 'DECLARE EMERGENCY'}
                                    </button>
                                    <button onClick={() => setShowCreate(false)} className="px-8 py-4 rounded-2xl border border-slate-800 text-slate-500 text-[11px] font-black uppercase tracking-widest hover:bg-slate-800 transition-all">ABORT</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}
            
            <style dangerouslySetInnerHTML={{ __html: `
                .custom-scrollbar::-webkit-scrollbar { width: 4px; }
                .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
                .custom-scrollbar::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 10px; }
                .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #334155; }
            `}} />
        </div>
    );
};

export default IncidentWarRoomDashboard;

