import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Plus, Search, Trash2, Upload, EyeOff } from 'lucide-react';
import type { AppView } from '../../types';
import { catalogueFor } from '../../utils/catalogueAccess';
import { isPlatformRoleName } from '../../utils/permissions';
import { fetchRoles } from '../../services/roleApi';
import {
  CatalogueWidget, DashboardApiError, DashboardDraft, Placement, createDashboard, deleteDashboard, getDashboard,
  getWidgetCatalogue, publishDashboard, saveDashboard, unpublishDashboard,
} from '../../services/dashboardsApi';
import { DashboardGrid, GRID_COLUMNS } from './DashboardGrid';

const EMPTY: DashboardDraft = { name: '', description: '', widgets: [], sharing: { everyone: false, roles: [] } };

const newInstanceId = (widgetId: string) => `${widgetId}-${Math.random().toString(36).slice(2, 8)}`.slice(0, 40);

/** Where a new widget goes: the left edge, below everything already placed. */
export function placeNew(widgets: Placement[], spec: CatalogueWidget): Placement {
  const bottom = widgets.reduce((max, w) => Math.max(max, w.y + w.h), 0);
  return { i: newInstanceId(spec.id), widget: spec.id, x: 0, y: bottom, w: spec.size.w, h: spec.size.h };
}

/** Arrow keys move the selected widget; Shift + arrows resize it, within the widget's limits. */
export function nudge(w: Placement, spec: CatalogueWidget | undefined, key: string, resize: boolean): Placement | null {
  const size = spec?.size ?? { minW: 1, minH: 1, maxH: 24, w: w.w, h: w.h };
  if (resize) {
    if (key === 'ArrowRight' && w.x + w.w < GRID_COLUMNS) return { ...w, w: w.w + 1 };
    if (key === 'ArrowLeft' && w.w > size.minW) return { ...w, w: w.w - 1 };
    if (key === 'ArrowDown' && w.h < size.maxH) return { ...w, h: w.h + 1 };
    if (key === 'ArrowUp' && w.h > size.minH) return { ...w, h: w.h - 1 };
    return null;
  }
  if (key === 'ArrowRight' && w.x + w.w < GRID_COLUMNS) return { ...w, x: w.x + 1 };
  if (key === 'ArrowLeft' && w.x > 0) return { ...w, x: w.x - 1 };
  if (key === 'ArrowDown') return { ...w, y: w.y + 1 };
  if (key === 'ArrowUp' && w.y > 0) return { ...w, y: w.y - 1 };
  return null;
}

interface StudioProps {
  dashboardId: string | null;
  onClose: (openId?: string) => void;
}

const field = 'w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/30 dark:border-white/[0.1] dark:bg-gray-900 dark:text-white';
const button = 'inline-flex h-10 items-center gap-2 rounded-xl px-4 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-50';

/** Dashboard Studio: a tenant admin arranges widgets of the screens their organization has. */
export function DashboardStudio({ dashboardId, onClose }: StudioProps) {
  const [id, setId] = useState<string | null>(dashboardId);
  const [draft, setDraft] = useState<DashboardDraft>(EMPTY);
  const [version, setVersion] = useState(0);
  const [status, setStatus] = useState<'draft' | 'published'>('draft');
  const [unpublished, setUnpublished] = useState(false);
  const [catalogue, setCatalogue] = useState<CatalogueWidget[]>([]);
  const [roles, setRoles] = useState<string[]>([]);
  const [unavailable, setUnavailable] = useState<Placement[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: 'error' | 'ok'; text: string } | null>(null);
  const [announce, setAnnounce] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const [cat, roleList, existing] = await Promise.all([
          getWidgetCatalogue(),
          fetchRoles().catch(() => []),
          dashboardId ? getDashboard(dashboardId, 'draft') : Promise.resolve(null),
        ]);
        if (!live) return;
        setCatalogue(cat.widgets);
        setRoles(roleList.map(r => r.name).filter(n => n && !isPlatformRoleName(n)));
        if (existing) {
          setDraft({ name: existing.name, description: existing.description || '', widgets: existing.widgets,
                     sharing: existing.sharing || EMPTY.sharing });
          setVersion(existing.version || 1);
          setStatus(existing.status);
          setUnpublished(!!existing.hasUnpublishedChanges);
          setUnavailable(existing.unavailable || []);
        }
      } catch (e) {
        if (live) setMessage({ tone: 'error', text: e instanceof Error ? e.message : "Couldn't load the studio" });
      } finally {
        if (live) setLoading(false);
      }
    })();
    return () => { live = false; };
  }, [dashboardId]);

  const byId = useMemo(() => Object.fromEntries(catalogue.map(w => [w.id, w])), [catalogue]);
  const available = catalogue.filter(w => w.available);
  const notBought = catalogue.length - available.length;
  const palette = useMemo(() => {
    const q = query.trim().toLowerCase();
    const groups = new Map<string, CatalogueWidget[]>();
    for (const w of available) {
      const source = catalogueFor(w.view as AppView)?.label || w.view;
      if (q && !`${w.title} ${source}`.toLowerCase().includes(q)) continue;
      groups.set(source, [...(groups.get(source) || []), w]);
    }
    return [...groups.entries()];
  }, [available, query]);

  const change = useCallback((next: Partial<DashboardDraft>) => {
    setDraft(d => ({ ...d, ...next }));
    setDirty(true);
    setMessage(null);
  }, []);

  const addWidget = (spec: CatalogueWidget) => {
    if (draft.widgets.length >= 40) {
      setMessage({ tone: 'error', text: 'A dashboard holds at most 40 widgets' });
      return;
    }
    const placed = placeNew(draft.widgets, spec);
    change({ widgets: [...draft.widgets, placed] });
    setSelected(placed.i);
    setAnnounce(`Added ${spec.title} at the bottom of the dashboard`);
  };

  const removeWidget = (i: string) => {
    const gone = draft.widgets.find(w => w.i === i);
    change({ widgets: draft.widgets.filter(w => w.i !== i) });
    if (selected === i) setSelected(null);
    if (gone) setAnnounce(`Removed ${byId[gone.widget]?.title || 'widget'}`);
  };

  const onKey = (i: string, e: React.KeyboardEvent) => {
    if (e.target !== e.currentTarget) return; // keys on the card's own buttons stay theirs
    if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault();
      removeWidget(i);
      return;
    }
    const current = draft.widgets.find(w => w.i === i);
    if (!current || !e.key.startsWith('Arrow')) return;
    e.preventDefault();
    const next = nudge(current, byId[current.widget], e.key, e.shiftKey);
    if (!next) return;
    change({ widgets: draft.widgets.map(w => (w.i === i ? next : w)) });
    const title = byId[current.widget]?.title || 'Widget';
    setAnnounce(e.shiftKey ? `${title} is ${next.w} columns wide and ${next.h} rows tall`
                           : `${title} moved to column ${next.x + 1}, row ${next.y + 1}`);
  };

  const fail = (e: unknown) => setMessage({ tone: 'error', text: e instanceof Error ? e.message : 'Something went wrong' });

  const save = async (): Promise<{ id: string; version: number } | null> => {
    if (!draft.name.trim()) {
      setMessage({ tone: 'error', text: 'Give the dashboard a name before saving' });
      return null;
    }
    setBusy('save');
    try {
      const saved = id ? await saveDashboard(id, draft, version) : await createDashboard(draft);
      setId(saved.id);
      setVersion(saved.version || 1);
      setUnpublished(!!saved.hasUnpublishedChanges);
      setDirty(false);
      setMessage({ tone: 'ok', text: saved.hasUnpublishedChanges ? 'Draft saved. Users still see the published version until you publish.' : 'Draft saved.' });
      return { id: saved.id, version: saved.version || 1 };
    } catch (e) {
      fail(e);
      return null;
    } finally {
      setBusy(null);
    }
  };

  const publish = async () => {
    const saved = dirty || !id ? await save() : { id: id as string, version };
    if (!saved) return;
    setBusy('publish');
    try {
      const done = await publishDashboard(saved.id, saved.version);
      setVersion(done.version || saved.version + 1);
      setStatus('published');
      setUnpublished(false);
      setMessage({ tone: 'ok', text: 'Published. Everyone it is shared with can open it under Dashboards.' });
    } catch (e) {
      fail(e);
    } finally {
      setBusy(null);
    }
  };

  const unpublish = async () => {
    if (!id) return;
    setBusy('unpublish');
    try {
      const done = await unpublishDashboard(id);
      setVersion(done.version || version + 1);
      setStatus('draft');
      setMessage({ tone: 'ok', text: 'Unpublished. Users no longer see this dashboard.' });
    } catch (e) { fail(e); } finally { setBusy(null); }
  };

  const remove = async () => {
    if (!id) { onClose(); return; }
    if (!window.confirm(`Delete "${draft.name || 'this dashboard'}"? Users who can see it lose it too.`)) return;
    setBusy('delete');
    try {
      await deleteDashboard(id);
      onClose();
    } catch (e) { fail(e); setBusy(null); }
  };

  const back = () => {
    if (dirty && !window.confirm('Leave without saving your changes?')) return;
    onClose(status === 'published' && id ? id : undefined);
  };

  const toggleRole = (role: string) => {
    const has = draft.sharing.roles.includes(role);
    change({ sharing: { ...draft.sharing, roles: has ? draft.sharing.roles.filter(r => r !== role) : [...draft.sharing.roles, role] } });
  };

  const audienceChosen = draft.sharing.everyone || draft.sharing.roles.length > 0;
  const statusLabel = status === 'published' ? (unpublished || dirty ? 'Published · changes not published' : 'Published') : 'Draft';

  if (loading) return <div className="p-8 text-sm text-gray-500 dark:text-gray-400">Loading the studio…</div>;

  return (
    <div className="space-y-4">
      <p className="sr-only" aria-live="polite">{announce}</p>
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={back} className={`${button} text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/[0.06]`}>
          <ArrowLeft className="h-4 w-4" /> Dashboards
        </button>
        <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${status === 'published'
          ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' : 'bg-gray-500/10 text-gray-700 dark:text-gray-300'}`}>{statusLabel}</span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {id && <button type="button" onClick={remove} disabled={!!busy} className={`${button} text-red-600 hover:bg-red-500/10 dark:text-red-400`}><Trash2 className="h-4 w-4" /> Delete</button>}
          {status === 'published' && <button type="button" onClick={unpublish} disabled={!!busy} className={`${button} text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/[0.06]`}><EyeOff className="h-4 w-4" /> Unpublish</button>}
          <button type="button" onClick={save} disabled={!!busy || !dirty} className={`${button} border border-gray-200 text-gray-800 hover:bg-gray-50 dark:border-white/[0.1] dark:text-gray-100 dark:hover:bg-white/[0.06]`}>
            {busy === 'save' ? 'Saving…' : 'Save draft'}
          </button>
          <button type="button" onClick={publish} disabled={!!busy || !audienceChosen || draft.widgets.length === 0}
                  title={!audienceChosen ? 'Choose who sees this dashboard first' : draft.widgets.length === 0 ? 'Add at least one widget' : undefined}
                  className={`${button} bg-primary-600 text-white hover:bg-primary-700`}>
            <Upload className="h-4 w-4" /> {busy === 'publish' ? 'Publishing…' : 'Publish'}
          </button>
        </div>
      </div>

      {message && (
        <p role={message.tone === 'error' ? 'alert' : 'status'}
           className={`rounded-xl px-4 py-2 text-sm ${message.tone === 'error' ? 'bg-red-500/10 text-red-700 dark:text-red-300' : 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'}`}>
          {message.text}
        </p>
      )}
      {unavailable.length > 0 && (
        <p className="rounded-xl bg-amber-500/10 px-4 py-2 text-sm text-amber-800 dark:text-amber-200">
          {unavailable.length} widget{unavailable.length === 1 ? " isn't" : "s aren't"} shown because {unavailable.length === 1 ? 'its screen is' : 'their screens are'} no longer available to your organization or role; saving drops {unavailable.length === 1 ? 'it' : 'them'} from the draft.
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <aside className="space-y-4">
          <section className="space-y-3 rounded-2xl border border-gray-200/80 bg-white p-4 shadow-card dark:border-white/[0.07] dark:bg-gray-800">
            <label className="block text-sm font-medium text-gray-800 dark:text-gray-100" htmlFor="dash-name">Name</label>
            <input id="dash-name" className={field} value={draft.name} maxLength={80} placeholder="e.g. Security operations"
                   onChange={e => change({ name: e.target.value })} />
            <label className="block text-sm font-medium text-gray-800 dark:text-gray-100" htmlFor="dash-desc">Description</label>
            <textarea id="dash-desc" className={field} rows={2} maxLength={280} value={draft.description}
                      onChange={e => change({ description: e.target.value })} />
          </section>

          <fieldset className="space-y-2 rounded-2xl border border-gray-200/80 bg-white p-4 shadow-card dark:border-white/[0.07] dark:bg-gray-800">
            <legend className="px-1 text-sm font-medium text-gray-800 dark:text-gray-100">Who sees it</legend>
            <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200">
              <input type="radio" name="audience" checked={draft.sharing.everyone}
                     onChange={() => change({ sharing: { everyone: true, roles: draft.sharing.roles } })} /> Everyone in the organization
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200">
              <input type="radio" name="audience" checked={!draft.sharing.everyone}
                     onChange={() => change({ sharing: { everyone: false, roles: draft.sharing.roles } })} /> Only these roles
            </label>
            {!draft.sharing.everyone && (
              <div className="ml-6 max-h-40 space-y-1 overflow-auto">
                {roles.length === 0 && <p className="text-xs text-gray-500 dark:text-gray-400">No roles found</p>}
                {roles.map(role => (
                  <label key={role} className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200">
                    <input type="checkbox" checked={draft.sharing.roles.includes(role)} onChange={() => toggleRole(role)} /> {role}
                  </label>
                ))}
              </div>
            )}
            <p className="text-xs text-gray-500 dark:text-gray-400">People only see widgets of screens their own role can open.</p>
          </fieldset>

          <section className="space-y-3 rounded-2xl border border-gray-200/80 bg-white p-4 shadow-card dark:border-white/[0.07] dark:bg-gray-800">
            <h2 className="text-sm font-medium text-gray-800 dark:text-gray-100">Widgets</h2>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" aria-hidden="true" />
              <input className={`${field} pl-9`} placeholder="Search widgets" aria-label="Search widgets" value={query} onChange={e => setQuery(e.target.value)} />
            </div>
            <div className="max-h-[28rem] space-y-3 overflow-auto pr-1">
              {palette.map(([source, items]) => (
                <div key={source}>
                  <p className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">{source}</p>
                  <ul className="space-y-1">
                    {items.map(w => (
                      <li key={w.id}>
                        <button type="button" onClick={() => addWidget(w)}
                                className="flex min-h-[44px] w-full items-center justify-between gap-2 rounded-xl px-3 py-2 text-left text-sm text-gray-800 hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:text-gray-100 dark:hover:bg-white/[0.06]">
                          <span>{w.title}</span><Plus className="h-4 w-4 shrink-0 text-primary-600 dark:text-primary-400" aria-label="Add" />
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
              {palette.length === 0 && <p className="text-sm text-gray-500 dark:text-gray-400">{available.length ? 'No widget matches that search' : 'No widgets are available to your organization yet'}</p>}
            </div>
            {notBought > 0 && (
              <p className="text-xs text-gray-500 dark:text-gray-400">{notBought} more widget{notBought === 1 ? '' : 's'} come with screens your organization or role doesn't have.</p>
            )}
          </section>
        </aside>

        <section aria-label="Dashboard layout" className="min-w-0 space-y-2">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Drag a widget by its title to move it and by its corner to resize it. With the keyboard: Tab to a widget, then arrow keys move it, Shift + arrows resize it, and Delete removes it.
          </p>
          {draft.widgets.length === 0 ? (
            <div className="flex min-h-[20rem] items-center justify-center rounded-2xl border-2 border-dashed border-gray-200 text-sm text-gray-500 dark:border-white/[0.1] dark:text-gray-400">
              Add widgets from the list to start
            </div>
          ) : (
            <DashboardGrid widgets={draft.widgets} catalogue={byId} editing selectedId={selected}
                           onLayoutChange={widgets => change({ widgets })} onRemove={removeWidget}
                           onSelect={setSelected} onKeyDown={onKey} />
          )}
        </section>
      </div>
    </div>
  );
}
