import React, { useCallback, useEffect, useState } from 'react';
import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { EyeOff, GripVertical, RefreshCw, Table2, BarChart3, X } from 'lucide-react';
import type { AppView } from '../../types';
import { catalogueFor } from '../../utils/catalogueAccess';
import type { CatalogueWidget, Placement } from '../../services/dashboardsApi';
import { Severity, WIDGET_LOADERS, WidgetData, WidgetLoadError } from './widgetData';

// Single-series magnitude: one hue (primary-500 reads on both themes). Severity is a state,
// so it uses the status colours the rest of the app uses, always next to its text label.
const BAR_HUE = '#0891B2';
const SEVERITY_HUE: Record<Severity, string> = { Critical: '#ef4444', High: '#f97316', Medium: '#f59e0b', Low: '#3b82f6' };

const compact = new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 });
const formatValue = (value: number, unit?: '%') => (unit === '%' ? `${value}%` : compact.format(value));

type LoadState = { data: WidgetData | null; error: string | null; loading: boolean };

/** Loads a widget's data once, and again on refresh; a refresh keeps the last render on screen. */
export function useWidgetData(widgetId: string): LoadState & { refresh: () => void } {
  const [state, setState] = useState<LoadState>({ data: null, error: null, loading: true });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const loader = WIDGET_LOADERS[widgetId];
    let live = true;
    setState(s => ({ ...s, loading: true }));
    if (!loader) {
      setState({ data: null, error: 'This widget is no longer available', loading: false });
      return;
    }
    loader()
      .then(data => { if (live) setState({ data, error: null, loading: false }); })
      .catch(e => {
        if (live) setState(s => ({ data: s.data, loading: false,
          error: e instanceof WidgetLoadError ? e.message : "Couldn't load" }));
      });
    return () => { live = false; };
  }, [widgetId, tick]);
  const refresh = useCallback(() => setTick(t => t + 1), []);
  return { ...state, refresh };
}

function Kpi({ data }: { data: Extract<WidgetData, { kind: 'kpi' }> }) {
  return (
    <div className="flex h-full flex-col justify-center">
      <p className="text-4xl font-semibold tracking-tight text-gray-900 dark:text-white">{formatValue(data.value, data.unit)}</p>
      {data.sub && <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{data.sub}</p>}
    </div>
  );
}

function BarTip({ active, payload, unit }: { active?: boolean; payload?: any[]; unit?: '%' }) {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;
  return (
    <div className="rounded-lg border border-gray-200/80 bg-white px-3 py-2 text-xs shadow-card dark:border-white/[0.07] dark:bg-gray-800">
      <p className="font-medium text-gray-900 dark:text-white">{item.label}</p>
      <p className="text-gray-600 dark:text-gray-300">{formatValue(item.value, unit)}</p>
    </div>
  );
}

function Bars({ data }: { data: Extract<WidgetData, { kind: 'bar' }> }) {
  if (!data.items.length || data.items.every(i => i.value === 0)) return <Empty text="Nothing to show yet" />;
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data.items} layout="vertical" margin={{ top: 4, right: 44, bottom: 4, left: 4 }} barCategoryGap={6}>
        <XAxis type="number" hide domain={[0, data.max ?? 'auto']} />
        <YAxis type="category" dataKey="label" width={96} axisLine={false} tickLine={false}
               tick={{ fontSize: 12, className: 'fill-gray-600 dark:fill-gray-300' }} />
        <Tooltip cursor={{ fill: 'rgba(99,112,137,0.08)' }} content={<BarTip unit={data.unit} />} />
        <Bar dataKey="value" barSize={16} radius={[0, 4, 4, 0]} isAnimationActive={false}>
          {data.items.map(item => (
            <Cell key={item.label} fill={item.severity ? SEVERITY_HUE[item.severity] : BAR_HUE} />
          ))}
          <LabelList dataKey="value" position="right" formatter={(v: unknown) => formatValue(Number(v), data.unit)}
                     className="fill-gray-700 dark:fill-gray-200 text-xs tabular-nums" />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function DataTable({ columns, rows, numeric = [] }: { columns: string[]; rows: (string | number)[][]; numeric?: number[] }) {
  if (!rows.length) return <Empty text="No records yet" />;
  return (
    <div className="h-full overflow-auto">
      <table className="w-full text-left text-sm">
        <thead className="sticky top-0 bg-white dark:bg-gray-800">
          <tr>{columns.map((c, n) => (
            <th key={c} scope="col" className={`py-1.5 pr-3 text-xs font-medium text-gray-500 dark:text-gray-400 ${numeric.includes(n) ? 'text-right' : ''}`}>{c}</th>
          ))}</tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r} className="border-t border-gray-100 dark:border-white/[0.06]">
              {row.map((cell, n) => (
                <td key={n} className={`py-1.5 pr-3 text-gray-800 dark:text-gray-200 ${numeric.includes(n) ? 'text-right tabular-nums' : ''}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Feed({ data }: { data: Extract<WidgetData, { kind: 'list' }> }) {
  if (!data.items.length) return <Empty text="No activity yet" />;
  return (
    <ul className="h-full space-y-2 overflow-auto text-sm">
      {data.items.map((item, n) => (
        <li key={n} className="flex items-baseline justify-between gap-3 border-b border-gray-100 pb-2 last:border-0 dark:border-white/[0.06]">
          <span className="min-w-0">
            <span className="block truncate font-medium text-gray-800 dark:text-gray-100">{item.primary}</span>
            {item.secondary && <span className="block truncate text-xs text-gray-500 dark:text-gray-400">{item.secondary}</span>}
          </span>
          {item.when && <span className="shrink-0 text-xs text-gray-500 dark:text-gray-400">{item.when}</span>}
        </li>
      ))}
    </ul>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="flex h-full items-center justify-center text-sm text-gray-500 dark:text-gray-400">{text}</div>;
}

const iconButton = 'inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:text-gray-400 dark:hover:bg-white/[0.06] dark:hover:text-white';

interface WidgetCardProps {
  placement: Placement;
  spec: CatalogueWidget | undefined;
  editing?: boolean;
  selected?: boolean;
  onRemove?: () => void;
  onHide?: () => void;
  onSelect?: () => void;
  onKeyDown?: (e: React.KeyboardEvent) => void;
}

/** One widget on a dashboard: header (title, source screen, actions) and its data. */
export function WidgetCard({ placement, spec, editing, selected, onRemove, onHide, onSelect, onKeyDown }: WidgetCardProps) {
  const { data, error, loading, refresh } = useWidgetData(placement.widget);
  const [asTable, setAsTable] = useState(false);
  const title = placement.title || spec?.title || 'Widget';
  const source = spec ? catalogueFor(spec.view as AppView)?.label : undefined;

  let body: React.ReactNode;
  if (!data && loading) body = <div className="h-full animate-pulse rounded-xl bg-gray-100 dark:bg-white/[0.04]" aria-label="Loading" />;
  else if (!data) body = <Empty text={error || "Couldn't load"} />;
  else if (data.kind === 'kpi') body = <Kpi data={data} />;
  else if (data.kind === 'bar') body = asTable
    ? <DataTable columns={['Category', 'Value']} numeric={[1]} rows={data.items.map(i => [i.label, formatValue(i.value, data.unit)])} />
    : <Bars data={data} />;
  else if (data.kind === 'table') body = <DataTable columns={data.columns} rows={data.rows} numeric={data.numeric} />;
  else body = <Feed data={data} />;

  return (
    <div role="group" aria-label={title} tabIndex={editing ? 0 : -1}
         onFocus={onSelect} onKeyDown={onKeyDown}
         className={`flex h-full flex-col overflow-hidden rounded-2xl border bg-white shadow-card dark:bg-gray-800 ${
           selected ? 'border-primary-500 ring-2 ring-primary-500/40' : 'border-gray-200/80 dark:border-white/[0.07]'} focus:outline-none`}>
      <div className={`flex items-start gap-1 px-4 pt-3 ${editing ? 'widget-drag cursor-grab active:cursor-grabbing' : ''}`}>
        {editing && <GripVertical className="mt-0.5 h-4 w-4 shrink-0 text-gray-400" aria-hidden="true" />}
        <div className="min-w-0 flex-1">
          <h3 className="line-clamp-2 break-words text-sm font-semibold leading-5 text-gray-900 dark:text-white">{title}</h3>
          {source && <p className="truncate text-xs text-gray-500 dark:text-gray-400">{source}</p>}
        </div>
        <div className="widget-actions flex shrink-0 items-center">
          {data?.kind === 'bar' && (
            <button type="button" className={iconButton} onClick={() => setAsTable(t => !t)}
                    aria-label={asTable ? `Show ${title} as a chart` : `Show ${title} as a table`} title={asTable ? 'Chart' : 'Table'}>
              {asTable ? <BarChart3 className="h-4 w-4" /> : <Table2 className="h-4 w-4" />}
            </button>
          )}
          {!editing && (
            <button type="button" className={iconButton} onClick={refresh} aria-label={`Refresh ${title}`} title="Refresh">
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin motion-reduce:animate-none' : ''}`} />
            </button>
          )}
          {onHide && (
            <button type="button" className={iconButton} onClick={onHide} aria-label={`Hide ${title} for me`} title="Hide for me">
              <EyeOff className="h-4 w-4" />
            </button>
          )}
          {onRemove && (
            <button type="button" className={iconButton} onClick={onRemove} aria-label={`Remove ${title}`} title="Remove">
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
      <div className={`min-h-0 flex-1 px-4 pb-4 pt-2 transition-opacity ${data && loading ? 'opacity-60' : ''}`}>
        {body}
        {data && error && <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">{error}; showing the last result</p>}
      </div>
    </div>
  );
}
