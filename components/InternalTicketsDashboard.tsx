import React, { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
const TicketReportsDashboard = lazy(() => import('./TicketReportsDashboard'));
import {
  Plus, Search, MessageSquare, ChevronRight, X, AlertCircle, CheckCircle,
  Clock, Circle, ArrowUp, ArrowDown, Minus, Trash2, Send, User, Paperclip,
  History, LayoutGrid, List, Timer, AlertTriangle, Link2, LogIn,
  ThumbsUp, ThumbsDown, Bell, BellOff, Tag, Settings, Filter,
  Download, Upload, BookTemplate, Zap, MoreHorizontal, CheckSquare, Square,
} from 'lucide-react';
import {
  fetchTickets, fetchTicketStats, createTicket, updateTicket, deleteTicket,
  addTicketComment, fetchTicketHistory, uploadTicketAttachment,
  deleteTicketAttachment, linkTickets, unlinkTickets, logTicketWork,
  escalateTicket, approveTicket, rejectTicket, addTicketWatcher,
  removeTicketWatcher, bulkUpdateTickets, fetchTicketTemplates,
  fetchTicketFieldSchema, fetchAgents, authFetch,
} from '../services/apiService';
import { useUser } from '../contexts/UserContext';
import { Agent } from '../types';
import { showToast } from '../utils/toast';

// ── Types ──────────────────────────────────────────────────────────────────────

interface WorkLog   { id: string; author: string; hours: number; description: string; created_at: string; }
interface Attachment { id: string; filename: string; size: number; mimetype: string; stored_as: string; uploaded_by: string; created_at: string; }
interface HistoryEntry { id: string; actor: string; action: string; changes: Record<string,any>; created_at: string; }
interface Comment   { id: string; author: string; text: string; created_at: string; }
interface TicketLink { linked_id: string; type: string; created_at: string; }

interface Ticket {
  id: string; ticket_number: string; title: string; description: string;
  type: string; priority: string; status: string;
  assignee: string; assignee_group: string; watchers: string[];
  reporter: string; tags: string[];
  due_date?: string; sla_hours?: number; sla_status?: string; sla_remaining_minutes?: number;
  escalated: boolean; escalation_level: number;
  approval_required: boolean; approval_status: string;
  approved_by?: string; rejected_by?: string; rejection_reason?: string;
  custom_fields: Record<string,any>;
  links: TicketLink[]; attachments: Attachment[];
  work_logs: WorkLog[]; total_hours_logged: number;
  comments: Comment[]; history: HistoryEntry[];
  created_at: string; updated_at: string;
  // Agent-raised context
  agent_id?: string;
  agent_hostname?: string;
  tenant_name?: string;
  endpoint_info?: Record<string,any>;
  // CSAT
  csat?: { rating: number; comment: string; submitted_by: string; submitted_at: string };
}

// ── Metadata maps ──────────────────────────────────────────────────────────────

const PRIORITY_META: Record<string,{label:string;color:string;bg:string;icon:React.ReactNode}> = {
  critical: { label:'Critical', color:'text-red-400',    bg:'bg-red-900/30',    icon:<ArrowUp size={11}/> },
  high:     { label:'High',     color:'text-orange-400', bg:'bg-orange-900/30', icon:<ArrowUp size={11}/> },
  medium:   { label:'Medium',   color:'text-yellow-400', bg:'bg-yellow-900/30', icon:<Minus size={11}/> },
  low:      { label:'Low',      color:'text-blue-400',   bg:'bg-blue-900/30',   icon:<ArrowDown size={11}/> },
};

const STATUS_META: Record<string,{label:string;color:string;bg:string;icon:React.ReactNode}> = {
  open:        { label:'Open',        color:'text-blue-400',   bg:'bg-blue-900/40',   icon:<Circle size={11}/> },
  in_progress: { label:'In Progress', color:'text-yellow-400', bg:'bg-yellow-900/40', icon:<Clock size={11}/> },
  resolved:    { label:'Resolved',    color:'text-green-400',  bg:'bg-green-900/40',  icon:<CheckCircle size={11}/> },
  closed:      { label:'Closed',      color:'text-slate-400',  bg:'bg-slate-700/40',  icon:<CheckCircle size={11}/> },
};

const TYPE_COLORS: Record<string,string> = {
  bug:      'bg-red-900/40 text-red-300',
  feature:  'bg-purple-900/40 text-purple-300',
  task:     'bg-blue-900/40 text-blue-300',
  incident: 'bg-orange-900/40 text-orange-300',
  security: 'bg-rose-900/40 text-rose-300',
};

const SLA_COLORS: Record<string,{text:string;bg:string}> = {
  ok:       { text:'text-green-400',  bg:'bg-green-900/30' },
  at_risk:  { text:'text-yellow-400', bg:'bg-yellow-900/30' },
  breached: { text:'text-red-400',    bg:'bg-red-900/30' },
  met:      { text:'text-slate-400',  bg:'bg-slate-700/30' },
  none:     { text:'text-slate-500',  bg:'bg-slate-800/30' },
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmt(iso: string) {
  return new Date(iso).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
}
function fmtTime(iso: string) {
  return new Date(iso).toLocaleString('en-US',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
}
function slaLabel(mins?: number) {
  if (mins === undefined) return '';
  if (mins < 60)  return `${mins}m`;
  if (mins < 1440) return `${Math.floor(mins/60)}h ${mins%60}m`;
  return `${Math.floor(mins/1440)}d`;
}
function fileSize(bytes: number) {
  if (bytes < 1024)        return `${bytes} B`;
  if (bytes < 1024*1024)   return `${(bytes/1024).toFixed(1)} KB`;
  return `${(bytes/(1024*1024)).toFixed(1)} MB`;
}

// ── Badges ────────────────────────────────────────────────────────────────────

const PriorityBadge = ({p}:{p:string}) => {
  const m = PRIORITY_META[p] ?? PRIORITY_META.medium;
  return <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded ${m.color} ${m.bg}`}>{m.icon}{m.label}</span>;
};
const StatusBadge = ({s}:{s:string}) => {
  const m = STATUS_META[s] ?? STATUS_META.open;
  return <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${m.color} ${m.bg}`}>{m.icon}{m.label}</span>;
};
const SlaBadge = ({status,mins}:{status?:string;mins?:number}) => {
  if (!status || status === 'none') return null;
  const c = SLA_COLORS[status] ?? SLA_COLORS.none;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${c.text} ${c.bg}`}>
      <Timer size={10}/>{status === 'breached' ? 'SLA Breached' : status === 'met' ? 'SLA Met' : slaLabel(mins)}
    </span>
  );
};

// ── Detail panel tab ──────────────────────────────────────────────────────────

type DetailTab = 'details'|'comments'|'history'|'attachments'|'worklog'|'links';

const TAB_CONFIG: {key:DetailTab;label:string;icon:React.ReactNode}[] = [
  { key:'details',     label:'Details',     icon:<AlertCircle size={13}/> },
  { key:'comments',    label:'Comments',    icon:<MessageSquare size={13}/> },
  { key:'history',     label:'History',     icon:<History size={13}/> },
  { key:'attachments', label:'Files',       icon:<Paperclip size={13}/> },
  { key:'worklog',     label:'Work Log',    icon:<Clock size={13}/> },
  { key:'links',       label:'Links',       icon:<Link2 size={13}/> },
];

// ── Create / Edit modal ───────────────────────────────────────────────────────

const TicketModal: React.FC<{
  onClose: () => void;
  onCreate: (t: Ticket) => void;
  templates: any[];
  fieldSchema: any[];
}> = ({ onClose, onCreate, templates, fieldSchema }) => {
  const [form, setForm] = useState<Record<string,any>>({
    title:'', description:'', type:'task', priority:'medium',
    assignee:'', assignee_group:'', tags:'', due_date:'',
    approval_required: false, custom_fields:{},
    agent_id:'', agent_hostname:'', tenant_name:'',
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState('');

  // Agent selector state
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentSearch, setAgentSearch] = useState('');
  const [agentDropOpen, setAgentDropOpen] = useState(false);
  const agentRef = React.useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchAgents().then(list => setAgents(Array.isArray(list) ? list : [])).catch(() => {});
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (agentRef.current && !agentRef.current.contains(e.target as Node)) setAgentDropOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const filteredAgents = agents.filter(a =>
    !agentSearch || a.hostname?.toLowerCase().includes(agentSearch.toLowerCase()) ||
    a.id?.toLowerCase().includes(agentSearch.toLowerCase())
  ).slice(0, 30);

  const selectAgent = (agent: Agent) => {
    setForm(p => ({
      ...p,
      agent_id:       agent.id,
      agent_hostname: agent.hostname,
      tenant_name:    (agent as any).tenantName || agent.tenantId || '',
    }));
    setAgentSearch(agent.hostname);
    setAgentDropOpen(false);
  };

  const clearAgent = () => {
    setForm(p => ({ ...p, agent_id:'', agent_hostname:'', tenant_name:'' }));
    setAgentSearch('');
  };

  const applyTemplate = (tid: string) => {
    const t = templates.find(x => x.id === tid);
    if (!t) return;
    const d = t.defaults || {};
    setForm(prev => ({
      ...prev,
      type:        d.type        || prev.type,
      priority:    d.priority    || prev.priority,
      assignee:    d.assignee    || prev.assignee,
      assignee_group: d.assignee_group || prev.assignee_group,
      tags:        (d.tags || []).join(', ') || prev.tags,
      title:       d.title_template || prev.title,
      description: d.body_template  || prev.description,
    }));
    setSelectedTemplate(tid);
  };

  const submit = async () => {
    if (!form.title.trim()) { setErr('Title is required'); return; }
    setSaving(true);
    try {
      const payload: Record<string,any> = {
        ...form,
        tags: form.tags ? form.tags.split(',').map((t: string) => t.trim()).filter(Boolean) : [],
        template_id: selectedTemplate || undefined,
      };
      // Only send agent fields when an agent was actually selected
      if (!form.agent_id) {
        delete payload.agent_id;
        delete payload.agent_hostname;
        delete payload.tenant_name;
      }
      const ticket = await createTicket(payload);
      onCreate(ticket);
      onClose();
    } catch (e: any) { setErr(e.message || 'Failed to create ticket'); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <h2 className="text-white font-semibold text-lg">New Ticket</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X size={18}/></button>
        </div>
        <div className="p-6 space-y-4">
          {err && <p className="text-red-400 text-sm bg-red-900/20 px-3 py-2 rounded-lg">{err}</p>}

          {templates.length > 0 && (
            <div>
              <label className="block text-slate-400 text-xs mb-1">Template</label>
              <select className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
                value={selectedTemplate} onChange={e => applyTemplate(e.target.value)}>
                <option value="">None — blank ticket</option>
                {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
          )}

          <div>
            <label className="block text-slate-400 text-xs mb-1">Title *</label>
            <input className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-teal-500"
              placeholder="Brief summary of the issue" value={form.title}
              onChange={e => setForm(p => ({...p, title: e.target.value}))} />
          </div>

          <div>
            <label className="block text-slate-400 text-xs mb-1">Description</label>
            <textarea rows={4} className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-teal-500 resize-none"
              placeholder="Detailed description..." value={form.description}
              onChange={e => setForm(p => ({...p, description: e.target.value}))} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-slate-400 text-xs mb-1">Type</label>
              <select className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
                value={form.type} onChange={e => setForm(p => ({...p, type: e.target.value}))}>
                {['task','bug','feature','incident','security'].map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-slate-400 text-xs mb-1">Priority</label>
              <select className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
                value={form.priority} onChange={e => setForm(p => ({...p, priority: e.target.value}))}>
                {['critical','high','medium','low'].map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-slate-400 text-xs mb-1">Assignee (email)</label>
              <input className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-teal-500"
                placeholder="user@example.com" value={form.assignee}
                onChange={e => setForm(p => ({...p, assignee: e.target.value}))} />
            </div>
            <div>
              <label className="block text-slate-400 text-xs mb-1">Team / Group</label>
              <input className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-teal-500"
                placeholder="e.g. Security Team" value={form.assignee_group}
                onChange={e => setForm(p => ({...p, assignee_group: e.target.value}))} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-slate-400 text-xs mb-1">Due Date</label>
              <input type="datetime-local" className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-teal-500"
                value={form.due_date} onChange={e => setForm(p => ({...p, due_date: e.target.value}))} />
            </div>
            <div>
              <label className="block text-slate-400 text-xs mb-1">SLA Hours (override)</label>
              <input type="number" min={1} className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-teal-500"
                placeholder="Auto from priority" value={form.sla_hours || ''}
                onChange={e => setForm(p => ({...p, sla_hours: e.target.value ? Number(e.target.value) : undefined}))} />
            </div>
          </div>

          <div>
            <label className="block text-slate-400 text-xs mb-1">Tags (comma-separated)</label>
            <input className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-teal-500"
              placeholder="security, urgent, customer-reported" value={form.tags}
              onChange={e => setForm(p => ({...p, tags: e.target.value}))} />
          </div>

          {/* Agent / Host selector */}
          <div className="border border-slate-700 rounded-xl p-3 space-y-2 bg-slate-800/30">
            <p className="text-slate-400 text-xs font-medium flex items-center gap-1.5">🖥 Agent / Host <span className="text-slate-600">(optional)</span></p>
            <div ref={agentRef} className="relative">
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
                  <input
                    className="w-full bg-slate-800 border border-slate-600 rounded-lg pl-7 pr-3 py-2 text-white text-sm focus:outline-none focus:border-teal-500"
                    placeholder="Search by hostname or agent ID…"
                    value={agentSearch}
                    onChange={e => { setAgentSearch(e.target.value); setAgentDropOpen(true); if (!e.target.value) clearAgent(); }}
                    onFocus={() => setAgentDropOpen(true)}
                  />
                </div>
                {form.agent_id && (
                  <button onClick={clearAgent} className="px-2 text-slate-500 hover:text-red-400"><X size={14}/></button>
                )}
              </div>
              {agentDropOpen && filteredAgents.length > 0 && (
                <div className="absolute z-50 mt-1 w-full bg-slate-800 border border-slate-600 rounded-xl shadow-xl max-h-48 overflow-y-auto">
                  {filteredAgents.map(a => (
                    <button key={a.id} onClick={() => selectAgent(a)}
                      className="w-full text-left px-3 py-2 hover:bg-slate-700 flex items-center justify-between gap-2">
                      <div>
                        <p className="text-white text-sm font-medium">{a.hostname}</p>
                        <p className="text-slate-500 text-xs font-mono">{a.id}</p>
                      </div>
                      <div className="text-right shrink-0">
                        <span className={`text-xs px-1.5 py-0.5 rounded ${a.status === 'Online' ? 'bg-green-900/40 text-green-400' : 'bg-slate-700 text-slate-400'}`}>{a.status}</span>
                        <p className="text-slate-600 text-xs mt-0.5">{a.ipAddress}</p>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
            {/* Show resolved context when agent selected */}
            {form.agent_id && (
              <div className="grid grid-cols-2 gap-2 mt-1 text-xs bg-teal-900/20 border border-teal-700/30 rounded-lg px-3 py-2">
                <div><span className="text-slate-500">Hostname</span><p className="text-white font-mono">{form.agent_hostname}</p></div>
                <div><span className="text-slate-500">Tenant</span><p className="text-white">{form.tenant_name || '—'}</p></div>
                <div className="col-span-2"><span className="text-slate-500">Agent ID</span><p className="text-slate-300 font-mono text-[10px] break-all">{form.agent_id}</p></div>
              </div>
            )}
          </div>

          {/* Custom fields from schema */}
          {fieldSchema.map((field: any) => (
            <div key={field.key}>
              <label className="block text-slate-400 text-xs mb-1">{field.label}</label>
              {field.type === 'select' ? (
                <select className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
                  value={form.custom_fields[field.key] || ''}
                  onChange={e => setForm(p => ({...p, custom_fields: {...p.custom_fields, [field.key]: e.target.value}}))}>
                  <option value="">Select…</option>
                  {(field.options || []).map((o: string) => <option key={o} value={o}>{o}</option>)}
                </select>
              ) : (
                <input className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-teal-500"
                  type={field.type === 'number' ? 'number' : 'text'}
                  placeholder={field.placeholder || ''}
                  value={form.custom_fields[field.key] || ''}
                  onChange={e => setForm(p => ({...p, custom_fields: {...p.custom_fields, [field.key]: e.target.value}}))} />
              )}
            </div>
          ))}

          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" className="rounded" checked={form.approval_required}
              onChange={e => setForm(p => ({...p, approval_required: e.target.checked}))} />
            <span className="text-slate-300 text-sm">Requires approval before processing</span>
          </label>
        </div>

        <div className="flex justify-end gap-3 px-6 pb-6">
          <button onClick={onClose} className="px-4 py-2 text-slate-400 text-sm hover:text-white">Cancel</button>
          <button onClick={submit} disabled={saving}
            className="px-5 py-2 bg-teal-600 hover:bg-teal-500 text-white text-sm rounded-lg disabled:opacity-50">
            {saving ? 'Creating…' : 'Create Ticket'}
          </button>
        </div>
      </div>
    </div>
  );
};

// ── Stat card ─────────────────────────────────────────────────────────────────

const StatCard = ({label,value,color,sub,active,onClick}:{label:string;value:number;color:string;sub?:string;active?:boolean;onClick?:()=>void}) => (
  <div onClick={onClick} className={`bg-slate-800/60 border rounded-xl p-4 flex flex-col gap-1 transition-all cursor-pointer
    ${active ? 'border-teal-500/50 bg-teal-900/10' : 'border-slate-700/60 hover:border-slate-600'}`}>
    <span className="text-xs text-slate-400">{label}</span>
    <span className={`text-2xl font-bold ${color}`}>{value}</span>
    {sub && <span className="text-[10px] text-slate-500">{sub}</span>}
  </div>
);

// ── Main dashboard ────────────────────────────────────────────────────────────

const InternalTicketsDashboard: React.FC<{ currentUserEmail?: string }> = ({ currentUserEmail = '' }) => {
  const { currentUser } = useUser();
  const userEmail = currentUserEmail || (currentUser as any)?.email || '';

  const [tickets,      setTickets]      = useState<Ticket[]>([]);
  const [stats,        setStats]        = useState<any>(null);
  const [loading,      setLoading]      = useState(true);
  const [selected,     setSelected]     = useState<Ticket | null>(null);
  const [activeTab,    setActiveTab]    = useState<DetailTab>('details');
  const [showCreate,   setShowCreate]   = useState(false);
  const [viewMode,     setViewMode]     = useState<'list'|'kanban'>('list');
  const [mainView,     setMainView]     = useState<'tickets'|'reports'>('tickets');
  const [templates,    setTemplates]    = useState<any[]>([]);
  const [fieldSchema,  setFieldSchema]  = useState<any[]>([]);

  // ── Filters
  const [search,          setSearch]          = useState('');
  const [filterStatus,    setFilterStatus]    = useState('');
  const [filterPriority,  setFilterPriority]  = useState('');
  const [filterType,      setFilterType]      = useState('');
  const [filterSla,       setFilterSla]       = useState('');
  const [overdueOnly,     setOverdueOnly]     = useState(false);
  const [myTicketsOnly,   setMyTicketsOnly]   = useState(false);
  const [showAdvFilters,  setShowAdvFilters]  = useState(false);
  const [sortBy,          setSortBy]          = useState('created_at');
  const [sortDir,         setSortDir]         = useState(-1);

  // ── Bulk select
  const [selected_ids, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkAction,   setBulkAction]  = useState('');

  // ── Detail panel state
  const [comment,     setComment]    = useState('');
  const [sending,     setSending]    = useState(false);
  const [history,     setHistory]    = useState<HistoryEntry[]>([]);
  const [histLoading, setHistLoading]= useState(false);
  const [linkId,      setLinkId]     = useState('');
  const [linkType,    setLinkType]   = useState('relates_to');
  const [workHours,   setWorkHours]  = useState('');
  const [workNote,    setWorkNote]   = useState('');
  const [approvalComment, setApprovalComment] = useState('');
  const [rejectReason,    setRejectReason]    = useState('');
  const [escalateReason,  setEscalateReason]  = useState('');
  const [watcherEmail,    setWatcherEmail]    = useState('');

  // ── New feature state ─────────────────────────────────────────────────────
  const [dragOverColumn,  setDragOverColumn]  = useState<string|null>(null);
  const [csatRating,      setCsatRating]      = useState(0);
  const [csatComment,     setCsatComment]     = useState('');
  const [mergeTargetId,   setMergeTargetId]   = useState('');
  const [mentionSuggest,  setMentionSuggest]  = useState<string[]>([]);
  const [editingTitle,    setEditingTitle]    = useState(false);
  const [titleDraft,      setTitleDraft]      = useState('');

  const fileInputRef = useRef<HTMLInputElement>(null);

  const bottomRef = useRef<HTMLDivElement>(null);

  // ── Load ──────────────────────────────────────────────────────────────────
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string,any> = {};
      if (filterStatus)   params.status        = filterStatus;
      if (filterPriority) params.priority      = filterPriority;
      if (filterType)     params.type          = filterType;
      if (filterSla)      params.sla_status    = filterSla;
      if (overdueOnly)    params.overdue_only  = true;
      if (search)         params.search        = search;
      if (myTicketsOnly && userEmail) params.reporter = userEmail;
      params.sort_by  = sortBy;
      params.sort_dir = sortDir;

      const [data, statsData] = await Promise.all([
        fetchTickets(params),
        fetchTicketStats(myTicketsOnly && userEmail ? { reporter: userEmail } : {}),
      ]);
      setTickets(data.tickets ?? []);
      setStats(statsData);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [filterStatus, filterPriority, filterType, filterSla, overdueOnly, search, myTicketsOnly, userEmail, sortBy, sortDir]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    fetchTicketTemplates().then(setTemplates).catch(() => {});
    fetchTicketFieldSchema().then(s => setFieldSchema(s.fields || [])).catch(() => {});
  }, []);

  // ── Detail helpers ────────────────────────────────────────────────────────

  const openTicket = async (t: Ticket) => {
    setSelected(t); setActiveTab('details'); setHistory([]);
    setCsatRating(0); setCsatComment(''); setMergeTargetId('');
    setEditingTitle(false); setMentionSuggest([]);
  };

  const loadHistory = async (t: Ticket) => {
    setHistLoading(true);
    try {
      const h = await fetchTicketHistory(t.id);
      setHistory(Array.isArray(h) ? h : []);
    } catch { setHistory([]); }
    finally { setHistLoading(false); }
  };

  useEffect(() => {
    if (selected && activeTab === 'history') loadHistory(selected);
  }, [activeTab, selected?.id]);

  useEffect(() => {
    if (activeTab === 'comments') bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [selected?.comments?.length, activeTab]);

  // ── Mutations ─────────────────────────────────────────────────────────────

  const handlePatch = async (updates: Record<string,any>) => {
    if (!selected) return;
    const t = await updateTicket(selected.id, updates);
    setSelected(t);
    setTickets(prev => prev.map(x => x.id === t.id ? t : x));
  };

  const handleComment = async () => {
    if (!selected || !comment.trim() || sending) return;
    setSending(true);
    try {
      const t = await addTicketComment(selected.id, comment.trim());
      setSelected(t);
      setTickets(prev => prev.map(x => x.id === t.id ? t : x));
      setComment('');
    } finally { setSending(false); }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!selected || !e.target.files?.[0]) return;
    const file = e.target.files[0];
    await uploadTicketAttachment(selected.id, file);
    const t = await fetchTickets({ }).then(() => null); // reload selected
    // Re-fetch just the selected ticket
    try {
      const { tickets: list } = await fetchTickets({});
      const fresh = list.find((x: Ticket) => x.id === selected.id);
      if (fresh) { setSelected(fresh); setTickets(prev => prev.map(x => x.id === fresh.id ? fresh : x)); }
    } catch (e) { console.error('Failed to reload ticket after attachment upload:', e); }
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleDeleteAttachment = async (attId: string) => {
    if (!selected) return;
    await deleteTicketAttachment(selected.id, attId);
    setSelected(prev => prev ? {...prev, attachments: prev.attachments.filter(a => a.id !== attId)} : prev);
  };

  const handleLogWork = async () => {
    if (!selected || !workHours || Number(workHours) <= 0) return;
    const t = await logTicketWork(selected.id, Number(workHours), workNote);
    setSelected(t); setWorkHours(''); setWorkNote('');
  };

  const handleLink = async () => {
    if (!selected || !linkId.trim()) return;
    const t = await linkTickets(selected.id, linkId.trim(), linkType);
    setSelected(t); setLinkId('');
  };

  const handleEscalate = async () => {
    if (!selected) return;
    const t = await escalateTicket(selected.id, escalateReason);
    setSelected(t); setTickets(prev => prev.map(x => x.id === t.id ? t : x)); setEscalateReason('');
  };

  const handleApprove = async () => {
    if (!selected) return;
    const t = await approveTicket(selected.id, approvalComment);
    setSelected(t); setTickets(prev => prev.map(x => x.id === t.id ? t : x)); setApprovalComment('');
  };

  const handleReject = async () => {
    if (!selected || !rejectReason.trim()) return;
    const t = await rejectTicket(selected.id, rejectReason);
    setSelected(t); setTickets(prev => prev.map(x => x.id === t.id ? t : x)); setRejectReason('');
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this ticket?')) return;
    await deleteTicket(id);
    setTickets(prev => prev.filter(t => t.id !== id));
    if (selected?.id === id) setSelected(null);
  };

  const handleCsat = async () => {
    if (!csatRating || !selected) return;
    try {
      const res = await authFetch(`/api/tickets/${selected.id}/csat`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({rating: csatRating, comment: csatComment}),
      });
      if (res.ok) {
        const data = await res.json();
        setSelected(s => s ? {...s, csat: data.csat} : s);
        setCsatRating(0); setCsatComment('');
      }
    } catch (e) { console.error('Failed to submit CSAT rating:', e); }
  };

  const handleMerge = async () => {
    if (!selected || !mergeTargetId.trim()) return;
    if (!window.confirm(`Merge TKT-${selected.ticket_number} into ${mergeTargetId}? This will close the current ticket.`)) return;
    try {
      const res = await authFetch(`/api/tickets/${selected.id}/merge`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({target_ticket_id: mergeTargetId.trim()}),
      });
      if (res.ok) {
        setTickets(prev => prev.filter(t => t.id !== selected.id));
        setSelected(null); setMergeTargetId('');
      } else {
        showToast('Merge failed — check the target ticket ID', 'error');
      }
    } catch (e) { console.error('Failed to merge tickets:', e); }
  };

  const handleBulkAction = async () => {
    if (!bulkAction || selected_ids.size === 0) return;
    const ids = Array.from(selected_ids);
    const [action, value] = bulkAction.split(':');
    const updates: Record<string,string> = action === 'status' ? { status: value } :
                                           action === 'priority' ? { priority: value } : {};
    if (action === 'delete') {
      if (!confirm(`Delete ${ids.length} tickets?`)) return;
      await Promise.all(ids.map(id => deleteTicket(id)));
      setTickets(prev => prev.filter(t => !ids.includes(t.id)));
    } else if (Object.keys(updates).length) {
      await bulkUpdateTickets(ids, updates);
    }
    setSelectedIds(new Set()); setBulkAction(''); load();
  };

  // ── Kanban ────────────────────────────────────────────────────────────────

  const kanbanCols = ['open','in_progress','resolved','closed'];
  const byStatus   = (s: string) => tickets.filter(t => t.status === s);

  // ── Stats ─────────────────────────────────────────────────────────────────

  const totalCount    = stats?.total ?? 0;
  const openCount     = stats?.by_status?.open ?? 0;
  const criticalCount = stats?.by_priority?.critical ?? 0;
  const overdueCount  = stats?.overdue ?? 0;
  const escalatedCnt  = stats?.escalated ?? 0;

  // ── RENDER ────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-full bg-slate-950 text-white overflow-hidden">

      {/* ── Left panel ──────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* Header */}
        <div className="px-6 pt-5 pb-3 border-b border-slate-800">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-1">
              <h1 className="text-xl font-semibold mr-3">Tickets</h1>
              {/* Main view toggle */}
              {(['tickets', 'reports'] as const).map(v => (
                <button key={v} onClick={() => setMainView(v)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold capitalize transition-colors
                    ${mainView === v
                      ? 'bg-teal-600 text-white'
                      : 'text-slate-400 hover:text-white hover:bg-slate-800'}`}>
                  {v === 'reports' ? '📊 Reports' : '🎫 Tickets'}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              {mainView === 'tickets' && (
                <>
                  <button onClick={() => setViewMode(v => v === 'list' ? 'kanban' : 'list')}
                    className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
                    title={viewMode === 'list' ? 'Kanban view' : 'List view'}>
                    {viewMode === 'list' ? <LayoutGrid size={16}/> : <List size={16}/>}
                  </button>
                  <button onClick={() => setShowCreate(true)}
                    className="flex items-center gap-2 px-4 py-2 bg-teal-600 hover:bg-teal-500 text-white text-sm rounded-lg transition-colors">
                    <Plus size={15}/> New Ticket
                  </button>
                </>
              )}
            </div>
          </div>

          {mainView === 'reports' && (
            <div className="text-xs text-slate-400 mt-1 mb-1">
              Showing aggregated analytics. Switch to <strong className="text-teal-400">🎫 Tickets</strong> to manage individual tickets.
            </div>
          )}

          {mainView === 'tickets' && (<>
          {/* Stats row */}
          <div className="grid grid-cols-5 gap-3 mb-4">
            <StatCard label="Total" value={totalCount} color="text-white" />
            <StatCard label="Open"  value={openCount}  color="text-blue-400"
              active={filterStatus==='open'} onClick={() => setFilterStatus(s => s==='open' ? '' : 'open')} />
            <StatCard label="Critical" value={criticalCount} color="text-red-400"
              active={filterPriority==='critical'} onClick={() => setFilterPriority(p => p==='critical' ? '' : 'critical')} />
            <StatCard label="Overdue"  value={overdueCount}  color="text-orange-400"
              active={overdueOnly} onClick={() => setOverdueOnly(p => !p)} />
            <StatCard label="Escalated" value={escalatedCnt} color="text-rose-400" />
          </div>

          {/* Search + filters */}
          <div className="flex items-center gap-2">
            <div className="flex-1 relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500"/>
              <input className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-teal-500"
                placeholder="Search tickets…" value={search} onChange={e => setSearch(e.target.value)} />
            </div>
            <select className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white"
              value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
              <option value="">All Status</option>
              {['open','in_progress','resolved','closed'].map(s => <option key={s} value={s}>{s.replace('_',' ')}</option>)}
            </select>
            <select className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white"
              value={filterPriority} onChange={e => setFilterPriority(e.target.value)}>
              <option value="">All Priority</option>
              {['critical','high','medium','low'].map(p => <option key={p} value={p}>{p}</option>)}
            </select>
            <select className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white"
              value={filterType} onChange={e => setFilterType(e.target.value)}>
              <option value="">All Types</option>
              {['bug','feature','task','incident','security'].map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <button onClick={() => setShowAdvFilters(v => !v)}
              className={`p-2 rounded-lg border transition-colors ${showAdvFilters ? 'border-teal-500 text-teal-400' : 'border-slate-700 text-slate-400 hover:text-white'}`}>
              <Filter size={15}/>
            </button>
          </div>

          {/* Advanced filters */}
          {showAdvFilters && (
            <div className="mt-2 flex items-center gap-2 flex-wrap">
              <select className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white"
                value={filterSla} onChange={e => setFilterSla(e.target.value)}>
                <option value="">SLA: All</option>
                {['ok','at_risk','breached','met'].map(s => <option key={s} value={s}>{s.replace('_',' ')}</option>)}
              </select>
              <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer">
                <input type="checkbox" checked={overdueOnly} onChange={e => setOverdueOnly(e.target.checked)} className="rounded"/>
                Overdue only
              </label>
              <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer">
                <input type="checkbox" checked={myTicketsOnly} onChange={e => setMyTicketsOnly(e.target.checked)} className="rounded"/>
                My tickets
              </label>
              <select className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white"
                value={`${sortBy}:${sortDir}`}
                onChange={e => { const [s,d] = e.target.value.split(':'); setSortBy(s); setSortDir(Number(d)); }}>
                <option value="created_at:-1">Newest first</option>
                <option value="created_at:1">Oldest first</option>
                <option value="due_date:1">Due date ↑</option>
                <option value="priority:-1">Priority ↓</option>
                <option value="updated_at:-1">Recently updated</option>
              </select>
            </div>
          )}

          {/* Bulk action bar */}
          {selected_ids.size > 0 && (
            <div className="mt-2 flex items-center gap-2 bg-teal-900/30 border border-teal-700/40 rounded-lg px-3 py-2">
              <span className="text-teal-300 text-xs font-medium">{selected_ids.size} selected</span>
              <select className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-white"
                value={bulkAction} onChange={e => setBulkAction(e.target.value)}>
                <option value="">Bulk action…</option>
                {['open','in_progress','resolved','closed'].map(s => <option key={s} value={`status:${s}`}>Set status: {s}</option>)}
                {['critical','high','medium','low'].map(p => <option key={p} value={`priority:${p}`}>Set priority: {p}</option>)}
                <option value="delete">Delete selected</option>
              </select>
              <button onClick={handleBulkAction} disabled={!bulkAction}
                className="px-3 py-1 bg-teal-600 hover:bg-teal-500 text-white text-xs rounded disabled:opacity-40">Apply</button>
              <button onClick={() => setSelectedIds(new Set())} className="ml-auto text-slate-400 hover:text-white">
                <X size={14}/>
              </button>
            </div>
          )}
          {/* end mainView tickets header section */}
          </>)}
        </div>

        {/* Content: list or kanban — tickets mode only */}
        {mainView === 'tickets' && (
        <div className="flex-1 overflow-auto">
          {loading ? (
            <div className="flex items-center justify-center h-40 text-slate-500 text-sm">Loading…</div>
          ) : viewMode === 'list' ? (
            /* ── List view ── */
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-900/90 border-b border-slate-800 z-10">
                <tr>
                  <th className="w-8 px-3 py-2">
                    <input type="checkbox" className="rounded"
                      checked={selected_ids.size === tickets.length && tickets.length > 0}
                      onChange={e => setSelectedIds(e.target.checked ? new Set(tickets.map(t => t.id)) : new Set())} />
                  </th>
                  {['ID','Title','Type','Priority','Status','SLA','Assignee','Due','Created'].map(h => (
                    <th key={h} className="px-3 py-2 text-left text-xs font-medium text-slate-400 whitespace-nowrap">{h}</th>
                  ))}
                  <th className="w-8"/>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {tickets.length === 0 ? (
                  <tr><td colSpan={11} className="text-center py-12 text-slate-500">No tickets found.</td></tr>
                ) : tickets.map(t => (
                  <tr key={t.id} onClick={() => openTicket(t)}
                    className={`cursor-pointer transition-colors hover:bg-slate-800/40 ${selected?.id === t.id ? 'bg-slate-800/60' : ''}`}>
                    <td className="px-3 py-2" onClick={e => e.stopPropagation()}>
                      <input type="checkbox" className="rounded"
                        checked={selected_ids.has(t.id)}
                        onChange={e => setSelectedIds(prev => { const s = new Set(prev); e.target.checked ? s.add(t.id) : s.delete(t.id); return s; })} />
                    </td>
                    <td className="px-3 py-2 text-slate-400 text-xs whitespace-nowrap font-mono">{t.ticket_number}</td>
                    <td className="px-3 py-2 max-w-[260px]">
                      <div className="truncate font-medium text-white">{t.title}</div>
                      <div className="flex items-center gap-1 mt-0.5 flex-wrap">
                        {t.escalated && <span className="text-[9px] bg-rose-900/40 text-rose-400 px-1.5 py-0.5 rounded font-semibold">ESCALATED</span>}
                        {t.approval_required && t.approval_status !== 'approved' &&
                          <span className="text-[9px] bg-amber-900/40 text-amber-400 px-1.5 py-0.5 rounded font-semibold">PENDING APPROVAL</span>}
                        {t.comments?.length > 0 && <span className="text-[10px] text-slate-500 flex items-center gap-0.5"><MessageSquare size={9}/>{t.comments.length}</span>}
                        {t.attachments?.length > 0 && <span className="text-[10px] text-slate-500 flex items-center gap-0.5"><Paperclip size={9}/>{t.attachments.length}</span>}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${TYPE_COLORS[t.type] ?? 'bg-slate-700 text-slate-300'}`}>{t.type}</span>
                    </td>
                    <td className="px-3 py-2"><PriorityBadge p={t.priority}/></td>
                    <td className="px-3 py-2"><StatusBadge s={t.status}/></td>
                    <td className="px-3 py-2"><SlaBadge status={t.sla_status} mins={t.sla_remaining_minutes}/></td>
                    <td className="px-3 py-2 text-slate-300 text-xs whitespace-nowrap">{t.assignee || <span className="text-slate-600">—</span>}</td>
                    <td className="px-3 py-2 text-xs whitespace-nowrap">
                      {t.due_date ? <span className={t.sla_status === 'breached' ? 'text-red-400 font-medium' : 'text-slate-400'}>{fmt(t.due_date)}</span> : <span className="text-slate-600">—</span>}
                    </td>
                    <td className="px-3 py-2 text-slate-500 text-xs whitespace-nowrap">{fmt(t.created_at)}</td>
                    <td className="px-3 py-2" onClick={e => e.stopPropagation()}>
                      <button onClick={e => handleDelete(t.id, e)} className="p-1 text-slate-600 hover:text-red-400 rounded transition-colors">
                        <Trash2 size={13}/>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            /* ── Kanban view ── */
            <div className="flex gap-4 p-4 h-full overflow-x-auto">
              {kanbanCols.map(col => {
                const m = STATUS_META[col];
                const colTickets = byStatus(col);
                const isOver = dragOverColumn === col;
                return (
                  <div key={col} className="flex-shrink-0 w-72 flex flex-col gap-3"
                    onDragOver={e => { e.preventDefault(); setDragOverColumn(col); }}
                    onDragEnter={e => { e.preventDefault(); setDragOverColumn(col); }}
                    onDragLeave={e => {
                      if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragOverColumn(null);
                    }}
                    onDrop={e => {
                      e.preventDefault();
                      setDragOverColumn(null);
                      const ticketId = e.dataTransfer.getData('ticketId');
                      if (!ticketId) return;
                      updateTicket(ticketId, {status: col}).then(updated => {
                        setTickets(prev => prev.map(t => t.id === ticketId ? updated : t));
                        if (selected?.id === ticketId) setSelected(updated);
                      }).catch(() => {});
                    }}>
                    <div className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors ${isOver ? 'ring-2 ring-teal-500' : ''} ${m.bg}`}>
                      {m.icon}
                      <span className={`text-sm font-semibold ${m.color}`}>{m.label}</span>
                      <span className="ml-auto text-xs text-slate-500">{colTickets.length}</span>
                    </div>
                    <div className={`flex flex-col gap-2 overflow-y-auto flex-1 min-h-[60px] rounded-xl transition-colors ${isOver ? 'bg-teal-900/10 ring-1 ring-teal-700/40' : ''}`}>
                      {colTickets.map(t => (
                        <div key={t.id}
                          draggable={true}
                          onDragStart={e => { e.dataTransfer.setData('ticketId', t.id); e.dataTransfer.effectAllowed = 'move'; }}
                          onClick={() => openTicket(t)}
                          className={`bg-slate-800/80 border border-slate-700/60 rounded-xl p-3 cursor-grab active:cursor-grabbing hover:border-teal-600/40 transition-all ${selected?.id===t.id ? 'border-teal-600/50' : ''}`}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-[10px] font-mono text-slate-500">{t.ticket_number}</span>
                            <PriorityBadge p={t.priority}/>
                          </div>
                          <p className="text-sm text-white font-medium line-clamp-2 mb-2">{t.title}</p>
                          <div className="flex items-center gap-1 flex-wrap">
                            {t.escalated && <span className="text-[9px] bg-rose-900/40 text-rose-400 px-1 py-0.5 rounded">ESC</span>}
                            <SlaBadge status={t.sla_status} mins={t.sla_remaining_minutes}/>
                            {t.due_date && <span className="text-[10px] text-slate-500">{fmt(t.due_date)}</span>}
                          </div>
                          {t.assignee && <p className="text-[10px] text-slate-500 mt-1 flex items-center gap-1"><User size={9}/>{t.assignee}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
        )} {/* end mainView === 'tickets' content */}

        {/* Reports view — inside left panel */}
        {mainView === 'reports' && (
          <div className="flex-1 overflow-y-auto px-6 py-4">
            <Suspense fallback={<div className="flex items-center justify-center h-40 text-slate-400 text-sm">Loading reports…</div>}>
              <TicketReportsDashboard />
            </Suspense>
          </div>
        )}
      </div> {/* end left panel */}

      {/* ── Detail panel — tickets mode only ─────────────────────── */}
      {mainView === 'tickets' && selected && (
        <div className="w-[480px] flex-shrink-0 border-l border-slate-800 flex flex-col bg-slate-900/50">
          {/* Panel header */}
          <div className="px-5 py-3 border-b border-slate-800 flex items-start gap-2">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-mono text-slate-500">{selected.ticket_number}</span>
                {selected.escalated && (
                  <span className="text-[9px] bg-rose-900/40 text-rose-400 px-1.5 py-0.5 rounded font-bold">
                    ESCALATED L{selected.escalation_level}
                  </span>
                )}
              </div>
              {editingTitle ? (
                <input autoFocus
                  className="bg-transparent border-b border-teal-500 text-white font-semibold text-sm w-full focus:outline-none"
                  value={titleDraft}
                  onChange={e => setTitleDraft(e.target.value)}
                  onBlur={() => { updateTicket(selected.id, {title: titleDraft}).then(t => setSelected(t)); setEditingTitle(false); }}
                  onKeyDown={e => {
                    if (e.key === 'Enter') { updateTicket(selected.id, {title: titleDraft}).then(t => setSelected(t)); setEditingTitle(false); }
                    if (e.key === 'Escape') setEditingTitle(false);
                  }}
                />
              ) : (
                <h3 onClick={() => { setEditingTitle(true); setTitleDraft(selected.title); }}
                  title="Click to edit"
                  className="font-semibold text-sm text-white leading-snug cursor-pointer hover:text-teal-300 transition-colors">{selected.title}</h3>
              )}
            </div>
            <button onClick={() => setSelected(null)} className="flex-shrink-0 p-1 text-slate-500 hover:text-white rounded transition-colors">
              <X size={16}/>
            </button>
          </div>

          {/* Status/priority quick actions */}
          <div className="px-5 py-2 border-b border-slate-800 flex items-center gap-2 flex-wrap">
            <StatusBadge s={selected.status}/>
            <PriorityBadge p={selected.priority}/>
            <SlaBadge status={selected.sla_status} mins={selected.sla_remaining_minutes}/>
            {['open','in_progress','resolved','closed']
              .filter(s => s !== selected.status)
              .map(s => (
                <button key={s} onClick={() => handlePatch({status: s})}
                  className="text-[10px] px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white rounded transition-colors">
                  → {s.replace('_',' ')}
                </button>
              ))}
          </div>

          {/* Tabs */}
          <div className="flex border-b border-slate-800 overflow-x-auto">
            {TAB_CONFIG.map(tab => (
              <button key={tab.key} onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium whitespace-nowrap border-b-2 transition-colors ${
                  activeTab === tab.key ? 'border-teal-500 text-teal-400' : 'border-transparent text-slate-500 hover:text-slate-300'}`}>
                {tab.icon}{tab.label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">

            {/* ── DETAILS ── */}
            {activeTab === 'details' && (
              <>
                {/* Agent context banner — shown when ticket was raised by/for an agent */}
                {(selected.agent_hostname || selected.agent_id) && (
                  <div className="rounded-lg border border-teal-700/50 bg-teal-900/20 px-3 py-2.5 flex items-start gap-2.5">
                    <span className="text-teal-400 mt-0.5">🖥</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-teal-300 text-xs font-semibold mb-1">Agent Context</p>
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                        <div>
                          <span className="text-slate-500">Hostname</span>
                          <p className="text-white font-mono truncate">{selected.agent_hostname || '—'}</p>
                        </div>
                        <div>
                          <span className="text-slate-500">Tenant</span>
                          <p className="text-white truncate">{selected.tenant_name || '—'}</p>
                        </div>
                        {selected.agent_id && (
                          <div className="col-span-2">
                            <span className="text-slate-500">Agent ID</span>
                            <p className="text-slate-300 font-mono text-[10px] break-all">{selected.agent_id}</p>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-3 text-sm">
                  {[
                    ['Reporter',  selected.reporter || '—'],
                    ['Assignee',  selected.assignee || '—'],
                    ['Team',      selected.assignee_group || '—'],
                    ['Type',      selected.type],
                    ['Due Date',  selected.due_date ? fmt(selected.due_date) : '—'],
                    ['SLA Hours', `${selected.sla_hours}h`],
                    ['Created',   fmt(selected.created_at)],
                    ['Updated',   fmt(selected.updated_at)],
                    ['Hours Logged', `${(selected.total_hours_logged || 0).toFixed(1)}h`],
                    ['Approval',  selected.approval_status || '—'],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <p className="text-slate-500 text-xs mb-0.5">{label}</p>
                      <p className="text-white text-xs font-medium">{value as string}</p>
                    </div>
                  ))}
                </div>

                {selected.description && (
                  <div>
                    <p className="text-slate-400 text-xs mb-1">Description</p>
                    <p className="text-slate-200 text-sm whitespace-pre-wrap bg-slate-800/50 rounded-lg p-3">{selected.description}</p>
                  </div>
                )}

                {selected.tags?.length > 0 && (
                  <div>
                    <p className="text-slate-400 text-xs mb-1">Tags</p>
                    <div className="flex flex-wrap gap-1">
                      {selected.tags.map(tag => (
                        <span key={tag} className="text-xs bg-slate-700 text-slate-300 px-2 py-0.5 rounded-full">{tag}</span>
                      ))}
                    </div>
                  </div>
                )}

                {/* ── Type-specific action panel ─────────────────────────── */}
                {(() => {
                  const tags = selected.tags || [];
                  const type = (selected.type || '').toLowerCase();
                  const info = selected.endpoint_info || {};
                  const isDone = ['resolved','closed','approved'].includes(selected.status);

                  if (tags.includes('install-software') || tags.includes('install_software')) {
                    const pkg  = info.package_name || info.software || selected.title.replace(/^.*request[:\s]*/i,'').trim();
                    const ver  = info.version ? ` v${info.version}` : '';
                    return (
                      <div className="rounded-xl border border-blue-700/40 bg-blue-900/15 p-3 space-y-2">
                        <p className="text-blue-300 text-xs font-semibold flex items-center gap-1.5">💿 Software Install Request</p>
                        <div className="flex items-center gap-2 bg-slate-800/60 rounded px-3 py-2">
                          <span className="text-slate-400 text-xs">Package:</span>
                          <span className="text-white text-xs font-mono font-semibold">{pkg}{ver}</span>
                          {info.installer_url && <a href={info.installer_url} target="_blank" rel="noreferrer" className="ml-auto text-xs text-blue-400 hover:underline">View installer ↗</a>}
                        </div>
                        {info.requested_by && <p className="text-slate-400 text-xs">Requested by: <span className="text-white">{info.requested_by}</span></p>}
                        {!isDone && !selected.approval_required && (
                          <div className="flex gap-2 pt-1">
                            <button onClick={handleApprove} className="flex-1 flex items-center justify-center gap-1 py-1.5 bg-green-700 hover:bg-green-600 text-white text-xs rounded font-medium">
                              <ThumbsUp size={11}/> Approve Install
                            </button>
                            <button onClick={() => setRejectReason('Not permitted on this host')} className="px-3 py-1.5 bg-red-800 hover:bg-red-700 text-white text-xs rounded">
                              <ThumbsDown size={11}/>
                            </button>
                          </div>
                        )}
                        {selected.approval_status === 'approved' && <p className="text-green-400 text-xs font-medium">✓ Install approved — agent will execute</p>}
                        {selected.approval_status === 'rejected' && <p className="text-red-400 text-xs font-medium">✗ Install denied{selected.rejection_reason ? `: ${selected.rejection_reason}` : ''}</p>}
                      </div>
                    );
                  }

                  if (tags.includes('access-request') || tags.includes('access_request') || type === 'access-request') {
                    const resource = info.resource || info.access_resource || '—';
                    const level    = info.access_level || info.permission_level || 'read';
                    return (
                      <div className="rounded-xl border border-purple-700/40 bg-purple-900/15 p-3 space-y-2">
                        <p className="text-purple-300 text-xs font-semibold flex items-center gap-1.5">🔑 Access Request</p>
                        <div className="grid grid-cols-2 gap-2 bg-slate-800/60 rounded px-3 py-2 text-xs">
                          <div><span className="text-slate-400">Resource:</span><p className="text-white font-medium">{resource}</p></div>
                          <div><span className="text-slate-400">Level:</span><p className="text-purple-300 font-medium capitalize">{level}</p></div>
                          {info.duration && <div><span className="text-slate-400">Duration:</span><p className="text-white">{info.duration}</p></div>}
                          {info.justification && <div className="col-span-2"><span className="text-slate-400">Justification:</span><p className="text-white">{info.justification}</p></div>}
                        </div>
                        {!isDone && (
                          <div className="flex gap-2 pt-1">
                            <button onClick={handleApprove} className="flex-1 flex items-center justify-center gap-1 py-1.5 bg-green-700 hover:bg-green-600 text-white text-xs rounded font-medium">
                              <ThumbsUp size={11}/> Grant Access
                            </button>
                            <div className="flex-1 flex gap-1">
                              <input className="flex-1 bg-slate-800 border border-slate-700 rounded px-2 text-xs text-white focus:outline-none"
                                placeholder="Deny reason…" value={rejectReason} onChange={e => setRejectReason(e.target.value)} />
                              <button onClick={handleReject} disabled={!rejectReason.trim()} className="px-2 bg-red-700 hover:bg-red-600 text-white text-xs rounded disabled:opacity-40">
                                <ThumbsDown size={11}/>
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  }

                  if (tags.includes('vulnerability') || tags.includes('cve') || type === 'security') {
                    return (
                      <div className="rounded-xl border border-rose-700/40 bg-rose-900/15 p-3 space-y-2">
                        <p className="text-rose-300 text-xs font-semibold flex items-center gap-1.5">🛡 Security Finding</p>
                        <div className="grid grid-cols-2 gap-2 text-xs">
                          {info.cve_id     && <div><span className="text-slate-400">CVE:</span><p className="text-rose-300 font-mono">{info.cve_id}</p></div>}
                          {info.cvss_score && <div><span className="text-slate-400">CVSS:</span><p className="text-white font-bold">{info.cvss_score}</p></div>}
                          {info.affected_component && <div className="col-span-2"><span className="text-slate-400">Component:</span><p className="text-white">{info.affected_component}</p></div>}
                        </div>
                        {!isDone && (
                          <div className="flex gap-2 pt-1">
                            <button onClick={() => updateTicket(selected.id, {status:'in_progress'}).then(t => setSelected(t))}
                              className="flex-1 py-1.5 bg-rose-700 hover:bg-rose-600 text-white text-xs rounded font-medium">
                              Start Remediation
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  }

                  if (tags.includes('config-change') || tags.includes('configuration') || type === 'change') {
                    return (
                      <div className="rounded-xl border border-yellow-700/40 bg-yellow-900/15 p-3 space-y-2">
                        <p className="text-yellow-300 text-xs font-semibold flex items-center gap-1.5">⚙ Configuration Change</p>
                        {info.config_key && <p className="text-xs text-slate-300 font-mono bg-slate-800/60 rounded px-2 py-1">{info.config_key}: {String(info.config_value ?? '—')}</p>}
                        {!isDone && (
                          <div className="flex gap-2 pt-1">
                            <button onClick={handleApprove} className="flex-1 flex items-center justify-center gap-1 py-1.5 bg-green-700 hover:bg-green-600 text-white text-xs rounded font-medium">
                              <ThumbsUp size={11}/> Approve Change
                            </button>
                            <button onClick={() => { setRejectReason('Change not approved'); handleReject(); }} className="px-3 py-1.5 bg-red-800 hover:bg-red-700 text-white text-xs rounded">
                              <ThumbsDown size={11}/>
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  }

                  return null;
                })()}

                {/* Watchers */}
                <div>
                  <p className="text-slate-400 text-xs mb-1">Watchers</p>
                  <div className="flex flex-wrap gap-1 mb-2">
                    {(selected.watchers || []).map(w => (
                      <span key={w} className="flex items-center gap-1 text-xs bg-slate-700 text-slate-300 px-2 py-0.5 rounded-full">
                        {w}
                        <button onClick={() => removeTicketWatcher(selected.id, w).then(t => { setSelected(t); })}
                          className="text-slate-500 hover:text-red-400"><X size={9}/></button>
                      </span>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <input className="flex-1 bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-teal-500"
                      placeholder="Add watcher email…" value={watcherEmail}
                      onChange={e => setWatcherEmail(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') { addTicketWatcher(selected.id, watcherEmail).then(()=>{}); setWatcherEmail(''); }}} />
                    <button onClick={() => { addTicketWatcher(selected.id, watcherEmail); setWatcherEmail(''); }}
                      className="px-2 py-1 bg-slate-700 hover:bg-slate-600 text-white text-xs rounded"><Bell size={12}/></button>
                  </div>
                </div>

                {/* Custom fields */}
                {Object.keys(selected.custom_fields || {}).length > 0 && (
                  <div>
                    <p className="text-slate-400 text-xs mb-1">Custom Fields</p>
                    <div className="space-y-1">
                      {Object.entries(selected.custom_fields).map(([k,v]) => (
                        <div key={k} className="flex justify-between text-xs">
                          <span className="text-slate-500 capitalize">{k.replace(/_/g,' ')}</span>
                          <span className="text-slate-200">{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Approval actions */}
                {selected.approval_required && selected.approval_status === 'pending' && (
                  <div className="bg-amber-900/20 border border-amber-700/30 rounded-xl p-3 space-y-2">
                    <p className="text-amber-400 text-xs font-semibold flex items-center gap-1"><AlertTriangle size={12}/> Pending Approval</p>
                    <input className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-white focus:outline-none"
                      placeholder="Optional comment…" value={approvalComment}
                      onChange={e => setApprovalComment(e.target.value)} />
                    <div className="flex gap-2">
                      <button onClick={handleApprove} className="flex-1 flex items-center justify-center gap-1 py-1.5 bg-green-700 hover:bg-green-600 text-white text-xs rounded">
                        <ThumbsUp size={11}/> Approve
                      </button>
                      <div className="flex-1 flex gap-1">
                        <input className="flex-1 bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-white focus:outline-none"
                          placeholder="Rejection reason (required)"
                          value={rejectReason} onChange={e => setRejectReason(e.target.value)} />
                        <button onClick={handleReject} disabled={!rejectReason.trim()}
                          className="px-2 bg-red-700 hover:bg-red-600 text-white text-xs rounded disabled:opacity-40">
                          <ThumbsDown size={11}/>
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* Escalate */}
                {!['resolved','closed'].includes(selected.status) && (
                  <div className="space-y-1">
                    <p className="text-slate-400 text-xs">Escalate</p>
                    <div className="flex gap-2">
                      <input className="flex-1 bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-white focus:outline-none focus:border-rose-500"
                        placeholder="Reason (optional)…" value={escalateReason}
                        onChange={e => setEscalateReason(e.target.value)} />
                      <button onClick={handleEscalate}
                        className="px-3 py-1.5 bg-rose-700 hover:bg-rose-600 text-white text-xs rounded flex items-center gap-1">
                        <Zap size={11}/> Escalate
                      </button>
                    </div>
                  </div>
                )}

                {/* Merge ticket */}
                {!['closed'].includes(selected.status) && (
                  <div className="space-y-1">
                    <p className="text-slate-400 text-xs">Merge into another ticket</p>
                    <div className="flex gap-2">
                      <input className="flex-1 bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-white focus:outline-none focus:border-purple-500"
                        placeholder="Target ticket ID (e.g. abc-123)…" value={mergeTargetId}
                        onChange={e => setMergeTargetId(e.target.value)} />
                      <button onClick={handleMerge} disabled={!mergeTargetId.trim()}
                        className="px-3 py-1.5 bg-purple-700 hover:bg-purple-600 text-white text-xs rounded disabled:opacity-40 font-medium whitespace-nowrap">
                        Merge
                      </button>
                    </div>
                  </div>
                )}

                {/* CSAT Rating */}
                {['resolved','closed'].includes(selected.status) && !selected.csat && (
                  <div className="rounded-xl border border-slate-700 bg-slate-800/30 p-3 space-y-2">
                    <p className="text-slate-400 text-xs font-medium">Rate this resolution</p>
                    <div className="flex gap-1">
                      {[1,2,3,4,5].map(n => (
                        <button key={n} onClick={() => setCsatRating(n)}
                          className={`text-xl transition-transform hover:scale-110 ${csatRating >= n ? 'text-yellow-400' : 'text-slate-600'}`}>★</button>
                      ))}
                    </div>
                    {csatRating > 0 && (
                      <>
                        <input className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-white"
                          placeholder="Optional comment…" value={csatComment} onChange={e => setCsatComment(e.target.value)} />
                        <button onClick={handleCsat} className="w-full py-1.5 bg-teal-700 hover:bg-teal-600 text-white text-xs rounded font-medium">
                          Submit Rating
                        </button>
                      </>
                    )}
                  </div>
                )}
                {selected.csat && (
                  <div className="text-xs text-slate-500 flex items-center gap-1">
                    {'★'.repeat(selected.csat.rating)}{'☆'.repeat(5 - selected.csat.rating)} rated by {selected.csat.submitted_by}
                  </div>
                )}
              </>
            )}

            {/* ── COMMENTS ── */}
            {activeTab === 'comments' && (
              <>
                <div className="space-y-3">
                  {(selected.comments || []).map(c => (
                    <div key={c.id} className="bg-slate-800/60 rounded-xl p-3">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-teal-400">{c.author}</span>
                        <span className="text-[10px] text-slate-500">{fmtTime(c.created_at)}</span>
                      </div>
                      <p className="text-sm text-slate-200 whitespace-pre-wrap">{c.text}</p>
                    </div>
                  ))}
                  {(!selected.comments || selected.comments.length === 0) &&
                    <p className="text-slate-500 text-sm text-center py-6">No comments yet.</p>}
                  <div ref={bottomRef}/>
                </div>
                {!['resolved','closed'].includes(selected.status) && (
                  <div className="sticky bottom-0 bg-slate-900/80 pt-2 flex gap-2 relative">
                    {mentionSuggest.length > 0 && (
                      <div className="absolute bottom-full mb-1 left-0 bg-slate-800 border border-slate-600 rounded-lg shadow-xl w-64 z-10">
                        {mentionSuggest.map(e => (
                          <button key={e} onClick={() => {
                            const newText = comment.replace(/@[\w.]*$/, `@${e} `);
                            setComment(newText); setMentionSuggest([]);
                          }} className="w-full text-left px-3 py-2 text-xs text-white hover:bg-slate-700">{e}</button>
                        ))}
                      </div>
                    )}
                    <textarea rows={2} className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-teal-500 resize-none"
                      placeholder="Add a comment… (Enter to send, @ to mention)" value={comment}
                      onChange={e => {
                        const val = e.target.value;
                        setComment(val);
                        const match = val.match(/@([\w.]*)$/);
                        if (match) {
                          const partial = match[1].toLowerCase();
                          const pool = [...(selected?.watchers || []), selected?.assignee, selected?.reporter].filter(Boolean) as string[];
                          setMentionSuggest(pool.filter(p => p.toLowerCase().includes(partial)).slice(0, 5));
                        } else {
                          setMentionSuggest([]);
                        }
                      }}
                      onKeyDown={e => { if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); handleComment(); }}} />
                    <button onClick={handleComment} disabled={sending || !comment.trim()}
                      className="px-3 bg-teal-600 hover:bg-teal-500 text-white rounded-xl disabled:opacity-40 flex-shrink-0">
                      <Send size={15}/>
                    </button>
                  </div>
                )}
              </>
            )}

            {/* ── HISTORY ── */}
            {activeTab === 'history' && (
              <div className="space-y-2">
                {histLoading ? <p className="text-slate-500 text-sm text-center py-6">Loading…</p> :
                  history.length === 0 ? <p className="text-slate-500 text-sm text-center py-6">No history yet.</p> :
                  history.map(h => (
                    <div key={h.id} className="flex gap-3 text-xs">
                      <div className="flex-shrink-0 mt-0.5 w-1.5 h-1.5 rounded-full bg-teal-500 mt-1.5"/>
                      <div className="flex-1">
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="font-medium text-slate-300">{h.actor}</span>
                          <span className="text-slate-600">{fmtTime(h.created_at)}</span>
                        </div>
                        <span className="text-slate-500 capitalize">{h.action.replace(/_/g,' ')}</span>
                        {Object.keys(h.changes).length > 0 && (
                          <div className="mt-0.5 space-y-0.5">
                            {Object.entries(h.changes).map(([k,v]: [string,any]) => (
                              <div key={k} className="text-slate-600">
                                {k}: {typeof v === 'object' ? `${v.from ?? '—'} → ${v.to ?? '—'}` : String(v)}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))
                }
              </div>
            )}

            {/* ── ATTACHMENTS ── */}
            {activeTab === 'attachments' && (
              <>
                <input ref={fileInputRef} type="file" className="hidden" onChange={handleUpload} />
                <button onClick={() => fileInputRef.current?.click()}
                  className="w-full flex items-center justify-center gap-2 py-2.5 border border-dashed border-slate-600 hover:border-teal-500 text-slate-400 hover:text-teal-400 rounded-xl text-sm transition-colors">
                  <Upload size={15}/> Upload File (max 20 MB)
                </button>
                <div className="space-y-2">
                  {(selected.attachments || []).map(a => (
                    <div key={a.id} className="flex items-center gap-3 bg-slate-800/60 rounded-xl p-3">
                      <Paperclip size={14} className="text-slate-400 flex-shrink-0"/>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-white truncate">{a.filename}</p>
                        <p className="text-[10px] text-slate-500">{fileSize(a.size)} · {a.uploaded_by} · {fmtTime(a.created_at)}</p>
                      </div>
                      <button onClick={() => handleDeleteAttachment(a.id)}
                        className="p-1 text-slate-600 hover:text-red-400 rounded transition-colors flex-shrink-0">
                        <Trash2 size={13}/>
                      </button>
                    </div>
                  ))}
                  {(!selected.attachments || selected.attachments.length === 0) &&
                    <p className="text-slate-500 text-sm text-center py-4">No files attached.</p>}
                </div>
              </>
            )}

            {/* ── WORK LOG ── */}
            {activeTab === 'worklog' && (
              <>
                <div className="bg-slate-800/60 rounded-xl p-3 flex items-center justify-between">
                  <span className="text-slate-400 text-sm">Total logged</span>
                  <span className="text-white font-semibold">{(selected.total_hours_logged || 0).toFixed(1)}h</span>
                </div>
                <div className="flex gap-2">
                  <input type="number" min={0.25} step={0.25} className="w-24 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-500"
                    placeholder="Hours" value={workHours} onChange={e => setWorkHours(e.target.value)} />
                  <input className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-500"
                    placeholder="Description…" value={workNote} onChange={e => setWorkNote(e.target.value)} />
                  <button onClick={handleLogWork} disabled={!workHours || Number(workHours) <= 0}
                    className="px-3 bg-teal-600 hover:bg-teal-500 text-white text-sm rounded-lg disabled:opacity-40">
                    Log
                  </button>
                </div>
                <div className="space-y-2">
                  {(selected.work_logs || []).map(w => (
                    <div key={w.id} className="flex gap-3 bg-slate-800/60 rounded-xl p-3 text-sm">
                      <LogIn size={14} className="text-slate-400 flex-shrink-0 mt-0.5"/>
                      <div className="flex-1">
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="text-teal-400 font-medium">{w.hours}h</span>
                          <span className="text-[10px] text-slate-500">{fmtTime(w.created_at)}</span>
                        </div>
                        <p className="text-slate-300">{w.description || <span className="text-slate-600">No description</span>}</p>
                        <p className="text-[10px] text-slate-600 mt-0.5">by {w.author}</p>
                      </div>
                    </div>
                  ))}
                  {(!selected.work_logs || selected.work_logs.length === 0) &&
                    <p className="text-slate-500 text-sm text-center py-4">No work logged yet.</p>}
                </div>
              </>
            )}

            {/* ── LINKS ── */}
            {activeTab === 'links' && (
              <>
                <div className="flex gap-2">
                  <input className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-teal-500"
                    placeholder="Ticket ID (e.g. TKT-0012)…" value={linkId}
                    onChange={e => setLinkId(e.target.value)} />
                  <select className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-2 text-sm text-white"
                    value={linkType} onChange={e => setLinkType(e.target.value)}>
                    {['blocks','blocked_by','relates_to','duplicates','duplicated_by','clones'].map(t => (
                      <option key={t} value={t}>{t.replace(/_/g,' ')}</option>
                    ))}
                  </select>
                  <button onClick={handleLink} disabled={!linkId.trim()}
                    className="px-3 bg-teal-600 hover:bg-teal-500 text-white text-sm rounded-lg disabled:opacity-40">
                    Link
                  </button>
                </div>
                <div className="space-y-2">
                  {(selected.links || []).map(l => (
                    <div key={l.linked_id} className="flex items-center gap-3 bg-slate-800/60 rounded-xl p-3">
                      <Link2 size={13} className="text-slate-400 flex-shrink-0"/>
                      <div className="flex-1">
                        <span className="text-xs text-slate-500 mr-2">{l.type.replace(/_/g,' ')}</span>
                        <span className="text-sm text-white font-mono">{l.linked_id}</span>
                      </div>
                      <button onClick={() => unlinkTickets(selected.id, l.linked_id).then(t => setSelected(t))}
                        className="p-1 text-slate-600 hover:text-red-400 rounded"><X size={12}/></button>
                    </div>
                  ))}
                  {(!selected.links || selected.links.length === 0) &&
                    <p className="text-slate-500 text-sm text-center py-4">No linked tickets.</p>}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── Create modal ── */}
      {showCreate && (
        <TicketModal
          onClose={() => setShowCreate(false)}
          onCreate={t => { setTickets(prev => [t, ...prev]); setSelected(t); setActiveTab('details'); }}
          templates={templates}
          fieldSchema={fieldSchema}
        />
      )}

    </div>
  );
};

export default InternalTicketsDashboard;
