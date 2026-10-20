import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Eye, LayoutDashboard, Pencil, Plus } from 'lucide-react';
import {
  CatalogueWidget, DashboardDetail, DashboardSummary, getDashboard, getWidgetCatalogue, listDashboards, setHiddenWidgets,
} from '../../services/dashboardsApi';
import { DashboardGrid } from './DashboardGrid';
import { DashboardStudio } from './DashboardStudio';

type Mode = { kind: 'list' } | { kind: 'view'; id: string } | { kind: 'studio'; id: string | null };

const button = 'inline-flex h-10 items-center gap-2 rounded-xl px-4 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50';
const card = 'rounded-2xl border border-gray-200/80 bg-white shadow-card dark:border-white/[0.07] dark:bg-gray-800';

const when = (iso?: string | null) => {
  const t = Date.parse(String(iso ?? ''));
  return Number.isNaN(t) ? '' : new Date(t).toLocaleDateString(undefined, { dateStyle: 'medium' });
};

/** One published dashboard as its audience sees it; each person may hide widgets for themselves. */
function DashboardView({ id, canDesign, onBack, onEdit }: { id: string; canDesign: boolean; onBack: () => void; onEdit: () => void }) {
  const [detail, setDetail] = useState<DashboardDetail | null>(null);
  const [catalogue, setCatalogue] = useState<Record<string, CatalogueWidget>>({});
  const [hidden, setHidden] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([getDashboard(id), getWidgetCatalogue()])
      .then(([d, cat]) => {
        if (!live) return;
        setDetail(d);
        setHidden(d.hidden);
        setCatalogue(Object.fromEntries(cat.widgets.map(w => [w.id, w])));
      })
      .catch(e => { if (live) setError(e instanceof Error ? e.message : "Couldn't open this dashboard"); });
    return () => { live = false; };
  }, [id]);

  const storeHidden = useCallback((next: string[]) => {
    const before = hidden;
    setHidden(next);
    setHiddenWidgets(id, next).catch(() => {
      setHidden(before);
      setError("Couldn't save your choice; try again");
    });
  }, [hidden, id]);

  if (error && !detail) return <p role="alert" className="rounded-xl bg-red-500/10 px-4 py-2 text-sm text-red-700 dark:text-red-300">{error}</p>;
  if (!detail) return <div className="p-8 text-sm text-gray-500 dark:text-gray-400">Loading…</div>;

  const shown = detail.widgets.filter(w => !hidden.includes(w.i));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start gap-3">
        <button type="button" onClick={onBack} className={`${button} text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/[0.06]`}>
          <ArrowLeft className="h-4 w-4" /> Dashboards
        </button>
        <div className="min-w-0 basis-full sm:basis-auto sm:flex-1">
          <h1 className="text-2xl font-semibold tracking-tight text-gray-900 dark:text-white">{detail.name}</h1>
          {detail.description && <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">{detail.description}</p>}
        </div>
        {canDesign && (
          <button type="button" onClick={onEdit} className={`${button} bg-primary-600 text-white hover:bg-primary-700`}>
            <Pencil className="h-4 w-4" /> Edit
          </button>
        )}
      </div>
      {error && <p role="alert" className="rounded-xl bg-red-500/10 px-4 py-2 text-sm text-red-700 dark:text-red-300">{error}</p>}
      {(hidden.length > 0 || detail.withheld > 0) && (
        <div className="flex flex-wrap items-center gap-3 text-sm text-gray-600 dark:text-gray-300">
          {hidden.length > 0 && (
            <span>
              You hid {hidden.length} widget{hidden.length === 1 ? '' : 's'}.{' '}
              <button type="button" className="font-medium text-primary-700 underline-offset-2 hover:underline dark:text-primary-400"
                      onClick={() => storeHidden([])}>Show all</button>
            </span>
          )}
          {detail.withheld > 0 && (
            <span>{detail.withheld} widget{detail.withheld === 1 ? " isn't" : "s aren't"} shown because your role can't open {detail.withheld === 1 ? 'its screen' : 'their screens'}.</span>
          )}
        </div>
      )}
      {shown.length === 0 ? (
        <div className={`${card} p-10 text-center text-sm text-gray-500 dark:text-gray-400`}>
          {detail.widgets.length ? 'Every widget is hidden.' : 'This dashboard has no widgets you can see.'}
        </div>
      ) : (
        <DashboardGrid widgets={shown} catalogue={catalogue} onHide={i => storeHidden([...hidden, i])} />
      )}
    </div>
  );
}

/** The Dashboards screen: the tenant's dashboards, the viewer, and (for designers) the Studio. */
export function DashboardsHub() {
  const [mode, setMode] = useState<Mode>({ kind: 'list' });
  const [dashboards, setDashboards] = useState<DashboardSummary[] | null>(null);
  const [canDesign, setCanDesign] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    listDashboards()
      .then(r => { setDashboards(r.dashboards); setCanDesign(r.canDesign); })
      .catch(e => { setDashboards([]); setError(e instanceof Error ? e.message : "Couldn't load dashboards"); });
  }, []);
  useEffect(() => { if (mode.kind === 'list') load(); }, [mode, load]);

  const sorted = useMemo(() => dashboards || [], [dashboards]);

  if (mode.kind === 'studio') {
    return <DashboardStudio dashboardId={mode.id} onClose={openId => setMode(openId ? { kind: 'view', id: openId } : { kind: 'list' })} />;
  }
  if (mode.kind === 'view') {
    return <DashboardView id={mode.id} canDesign={canDesign} onBack={() => setMode({ kind: 'list' })}
                          onEdit={() => setMode({ kind: 'studio', id: mode.id })} />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-gray-900 dark:text-white">Dashboards</h1>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
            {canDesign ? 'Design dashboards from the screens your organization has, and choose who sees each one.'
                       : 'Dashboards your administrator shared with you.'}
          </p>
        </div>
        {canDesign && (
          <button type="button" onClick={() => setMode({ kind: 'studio', id: null })} className={`${button} bg-primary-600 text-white hover:bg-primary-700`}>
            <Plus className="h-4 w-4" /> New dashboard
          </button>
        )}
      </div>
      {error && <p role="alert" className="rounded-xl bg-red-500/10 px-4 py-2 text-sm text-red-700 dark:text-red-300">{error}</p>}
      {dashboards === null ? (
        <div className="p-8 text-sm text-gray-500 dark:text-gray-400">Loading…</div>
      ) : sorted.length === 0 ? (
        <div className={`${card} flex flex-col items-center gap-3 p-10 text-center`}>
          <LayoutDashboard className="h-8 w-8 text-primary-600 dark:text-primary-400" aria-hidden="true" />
          <p className="text-sm text-gray-600 dark:text-gray-300">
            {canDesign ? 'No dashboards yet. Create one from the widgets of the screens your organization has.'
                       : "Your administrator hasn't shared a dashboard with you yet."}
          </p>
        </div>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {sorted.map(d => {
            const openable = d.status === 'published';
            return (
              <li key={d.id} className={`${card} flex flex-col gap-3 p-5`}>
                <div className="flex items-start justify-between gap-3">
                  <h2 className="min-w-0 truncate text-base font-semibold text-gray-900 dark:text-white">{d.name}</h2>
                  {canDesign && (
                    <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${d.status === 'published'
                      ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' : 'bg-gray-500/10 text-gray-700 dark:text-gray-300'}`}>
                      {d.status === 'published' ? (d.hasUnpublishedChanges ? 'Published · edits pending' : 'Published') : 'Draft'}
                    </span>
                  )}
                </div>
                {d.description && <p className="line-clamp-2 text-sm text-gray-600 dark:text-gray-300">{d.description}</p>}
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {d.widgetCount} widget{d.widgetCount === 1 ? '' : 's'}
                  {canDesign && d.sharing && ` · ${d.sharing.everyone ? 'Everyone' : d.sharing.roles.length ? d.sharing.roles.join(', ') : 'Not shared yet'}`}
                  {when(d.publishedAt || d.updatedAt) && ` · ${when(d.publishedAt || d.updatedAt)}`}
                </p>
                <div className="mt-auto flex gap-2">
                  {openable && (
                    <button type="button" onClick={() => setMode({ kind: 'view', id: d.id })}
                            className={`${button} border border-gray-200 text-gray-800 hover:bg-gray-50 dark:border-white/[0.1] dark:text-gray-100 dark:hover:bg-white/[0.06]`}>
                      <Eye className="h-4 w-4" /> Open
                    </button>
                  )}
                  {canDesign && (
                    <button type="button" onClick={() => setMode({ kind: 'studio', id: d.id })}
                            className={`${button} text-primary-700 hover:bg-primary-500/10 dark:text-primary-400`}>
                      <Pencil className="h-4 w-4" /> Edit
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
