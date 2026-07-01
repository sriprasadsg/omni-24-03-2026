import React, { useState, useEffect, useCallback } from 'react';

const API = '/api/agent-groups';

interface Group {
  id: string;
  name: string;
  description: string;
  color: string;
  tags: string[];
  member_count: number;
  created_at: string;
}

interface Member {
  agent_id: string;
  hostname?: string;
  platform?: string;
  status?: string;
  ip_address?: string;
  added_at: string;
}

interface AgentOption {
  id: string;
  hostname: string;
  platform: string;
  status: string;
}

const MOCK_GROUPS: Group[] = [
  { id: 'g1', name: 'Windows Servers', description: 'All Windows server endpoints', color: '#3b82f6', tags: ['windows', 'servers'], member_count: 12, created_at: '2026-05-01T00:00:00Z' },
  { id: 'g2', name: 'Linux Workstations', description: 'Developer and analyst Linux workstations', color: '#10b981', tags: ['linux', 'workstations'], member_count: 8, created_at: '2026-05-10T00:00:00Z' },
  { id: 'g3', name: 'DMZ Hosts', description: 'Hosts in the demilitarized zone', color: '#f59e0b', tags: ['dmz', 'network'], member_count: 5, created_at: '2026-05-15T00:00:00Z' },
  { id: 'g4', name: 'Critical Assets', description: 'High-value targets requiring strict monitoring', color: '#ef4444', tags: ['critical'], member_count: 3, created_at: '2026-05-20T00:00:00Z' },
];

const token = () => localStorage.getItem('token') ?? '';
const h = () => ({ Authorization: `Bearer ${token()}` });
const jh = () => ({ ...h(), 'Content-Type': 'application/json' });

export default function AgentGroupsDashboard() {
  const [groups, setGroups] = useState<Group[]>(MOCK_GROUPS);
  const [selected, setSelected] = useState<Group | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', description: '', color: '#3b82f6', tags: '' });
  const [saving, setSaving] = useState(false);
  const [addAgentId, setAddAgentId] = useState('');
  const [error, setError] = useState('');

  const loadGroups = useCallback(async () => {
    try {
      const r = await fetch(`${API}/`, { headers: h() });
      if (r.ok) {
        const data = await r.json();
        if (Array.isArray(data) && data.length > 0) setGroups(data);
      }
    } catch { /* use mock */ }
  }, []);

  const loadMembers = useCallback(async (group: Group) => {
    setSelected(group);
    setMembers([]);
    try {
      const r = await fetch(`${API}/${group.id}/members`, { headers: h() });
      if (r.ok) setMembers(await r.json());
    } catch { /* empty */ }
  }, []);

  useEffect(() => { loadGroups(); }, [loadGroups]);

  const createGroup = async () => {
    if (!form.name.trim()) return;
    setSaving(true);
    setError('');
    try {
      const r = await fetch(`${API}/`, {
        method: 'POST',
        headers: jh(),
        body: JSON.stringify({
          name: form.name,
          description: form.description,
          color: form.color,
          tags: form.tags.split(',').map(t => t.trim()).filter(Boolean),
        }),
      });
      if (r.ok) {
        const g = await r.json();
        setGroups(prev => [g, ...prev]);
        setShowCreate(false);
        setForm({ name: '', description: '', color: '#3b82f6', tags: '' });
      } else {
        const d = await r.json();
        setError(d.detail ?? 'Failed to create group');
      }
    } catch { setError('Network error'); }
    setSaving(false);
  };

  const deleteGroup = async (id: string) => {
    try {
      await fetch(`${API}/${id}`, { method: 'DELETE', headers: h() });
      setGroups(prev => prev.filter(g => g.id !== id));
      if (selected?.id === id) setSelected(null);
    } catch { /* ignore */ }
  };

  const addMember = async () => {
    if (!selected || !addAgentId.trim()) return;
    try {
      const r = await fetch(`${API}/${selected.id}/members`, {
        method: 'POST',
        headers: jh(),
        body: JSON.stringify({ agent_ids: [addAgentId.trim()] }),
      });
      if (r.ok) {
        setAddAgentId('');
        loadMembers(selected);
      }
    } catch { /* ignore */ }
  };

  const removeMember = async (agentId: string) => {
    if (!selected) return;
    try {
      await fetch(`${API}/${selected.id}/members/${agentId}`, { method: 'DELETE', headers: h() });
      setMembers(prev => prev.filter(m => m.agent_id !== agentId));
    } catch { /* ignore */ }
  };

  const STATUS_DOT: Record<string, string> = {
    active: 'bg-emerald-400', inactive: 'bg-slate-500', disconnected: 'bg-red-400',
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Agent Groups</h2>
        <button onClick={() => setShowCreate(true)}
          className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors">
          + New Group
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {groups.map(g => (
          <div key={g.id} className="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3 cursor-pointer hover:border-blue-500/50 transition-colors"
            onClick={() => loadMembers(g)}>
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: g.color }} />
                <span className="font-semibold text-white">{g.name}</span>
              </div>
              <button onClick={e => { e.stopPropagation(); deleteGroup(g.id); }}
                className="text-slate-500 hover:text-red-400 text-xs px-1.5 py-0.5 rounded transition-colors">
                Delete
              </button>
            </div>
            <p className="text-xs text-slate-400">{g.description}</p>
            <div className="flex flex-wrap gap-1">
              {g.tags.map(t => (
                <span key={t} className="text-xs px-1.5 py-0.5 rounded bg-slate-700 text-slate-300">{t}</span>
              ))}
            </div>
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>{g.member_count} agent{g.member_count !== 1 ? 's' : ''}</span>
              <span>Created {new Date(g.created_at).toLocaleDateString()}</span>
            </div>
          </div>
        ))}
      </div>

      {selected && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={() => setSelected(null)}>
          <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-2xl p-6 space-y-4 max-h-[80vh] overflow-y-auto"
            onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: selected.color }} />
                <h3 className="text-lg font-bold text-white">{selected.name}</h3>
              </div>
              <button onClick={() => setSelected(null)} className="text-slate-400 hover:text-white">&times;</button>
            </div>

            <div className="flex gap-2">
              <input value={addAgentId} onChange={e => setAddAgentId(e.target.value)}
                placeholder="Agent ID to add..."
                className="flex-1 bg-slate-800 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500" />
              <button onClick={addMember}
                className="px-3 py-1.5 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700 transition-colors">
                Add
              </button>
            </div>

            {members.length === 0 ? (
              <div className="text-slate-400 text-sm text-center py-8">No members in this group.</div>
            ) : (
              <div className="space-y-2">
                {members.map(m => (
                  <div key={m.agent_id} className="flex items-center gap-3 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2">
                    <div className={`w-2 h-2 rounded-full shrink-0 ${STATUS_DOT[m.status ?? ''] ?? 'bg-slate-500'}`} />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-white">{m.hostname ?? m.agent_id}</div>
                      <div className="text-xs text-slate-400">{m.platform} · {m.ip_address}</div>
                    </div>
                    <button onClick={() => removeMember(m.agent_id)}
                      className="text-slate-500 hover:text-red-400 text-xs transition-colors">
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-white">New Agent Group</h3>
              <button onClick={() => setShowCreate(false)} className="text-slate-400 hover:text-white">&times;</button>
            </div>
            {error && <div className="text-red-400 text-sm">{error}</div>}
            {[
              { label: 'Name *', key: 'name', placeholder: 'Group name' },
              { label: 'Description', key: 'description', placeholder: 'Optional description' },
              { label: 'Tags (comma-separated)', key: 'tags', placeholder: 'windows, servers' },
            ].map(f => (
              <div key={f.key} className="space-y-1">
                <label className="text-xs text-slate-400">{f.label}</label>
                <input value={(form as any)[f.key]} onChange={e => setForm(prev => ({ ...prev, [f.key]: e.target.value }))}
                  placeholder={f.placeholder}
                  className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
              </div>
            ))}
            <div className="space-y-1">
              <label className="text-xs text-slate-400">Color</label>
              <div className="flex gap-2 flex-wrap">
                {['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'].map(c => (
                  <button key={c} onClick={() => setForm(prev => ({ ...prev, color: c }))}
                    className={`w-6 h-6 rounded-full border-2 transition-all ${form.color === c ? 'border-white scale-110' : 'border-transparent'}`}
                    style={{ backgroundColor: c }} />
                ))}
              </div>
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setShowCreate(false)} className="flex-1 py-2 rounded-lg border border-slate-600 text-slate-300 text-sm hover:bg-slate-800 transition-colors">Cancel</button>
              <button onClick={createGroup} disabled={saving || !form.name.trim()}
                className="flex-1 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50">
                {saving ? 'Creating…' : 'Create Group'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
