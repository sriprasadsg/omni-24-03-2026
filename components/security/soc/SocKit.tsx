import React from 'react';
import { AlertCircle, AlertOctagon, AlertTriangle, Info } from 'lucide-react';
import { RESOLUTION_LABEL, SEVERITY_META, STATUS_LABEL, type AlertStatus, type Resolution, type Severity } from './socData';

// Small pieces shared by the SOC console's panels, queue and drawer. Severity always travels with
// an icon and a label, never colour alone.

export const SEVERITY_ICON: Record<Severity, React.ElementType> = {
    critical: AlertOctagon, high: AlertTriangle, medium: AlertCircle, low: Info, info: Info,
};

export const SeverityIcon: React.FC<{ severity: Severity; className?: string }> = ({ severity, className = 'w-3.5 h-3.5' }) => {
    const Icon = SEVERITY_ICON[severity];
    return <Icon className={`${className} ${SEVERITY_META[severity].text}`} aria-hidden="true" />;
};

export const SeverityBadge: React.FC<{ severity: Severity }> = ({ severity }) => (
    <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-semibold ring-1 ring-inset whitespace-nowrap ${SEVERITY_META[severity].chip}`}>
        <SeverityIcon severity={severity} className="w-3 h-3" />
        {SEVERITY_META[severity].label}
    </span>
);

export const StatusText: React.FC<{ status: AlertStatus; resolution?: Resolution | null }> = ({ status, resolution }) => (
    <span className="inline-flex items-center gap-1.5 text-[13px] text-gray-700 dark:text-gray-300 whitespace-nowrap">
        <span className={`h-1.5 w-1.5 rounded-full ${status === 'open' ? 'bg-primary-500 dark:bg-primary-400' : status === 'acknowledged' ? 'bg-amber-500' : 'bg-gray-400'}`} aria-hidden="true" />
        {status === 'closed' && resolution ? `Closed · ${RESOLUTION_LABEL[resolution]}` : STATUS_LABEL[status]}
    </span>
);

/** Per-severity counts as icon + number pairs (zeros left out). */
export const SeverityCounts: React.FC<{ counts: Partial<Record<Severity, number>>; className?: string }> = ({ counts, className = '' }) => {
    const shown = (Object.keys(SEVERITY_META) as Severity[]).filter(s => (counts[s] ?? 0) > 0);
    if (!shown.length) return <span className="text-xs text-gray-500 dark:text-gray-400">None</span>;
    return (
        <span className={`inline-flex flex-wrap items-center gap-x-2.5 gap-y-1 ${className}`}>
            {shown.map(s => (
                <span key={s} className="inline-flex items-center gap-1 text-xs tabular-nums text-gray-700 dark:text-gray-300" title={SEVERITY_META[s].label}>
                    <SeverityIcon severity={s} className="w-3 h-3" />
                    {counts[s]}<span className="sr-only"> {SEVERITY_META[s].label.toLowerCase()}</span>
                </span>
            ))}
        </span>
    );
};

export const subhead = 'text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400';

export const segmented = 'inline-flex h-9 p-0.5 rounded-xl border border-gray-200/80 dark:border-white/[0.08] bg-white dark:bg-gray-800';
export const segment = (on: boolean) => `px-2.5 rounded-[10px] text-sm font-medium transition-colors whitespace-nowrap ${on
    ? 'bg-primary-500/10 text-primary-700 dark:text-primary-300'
    : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white'}`;
export const field = 'h-9 rounded-xl text-sm bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.08] text-gray-900 dark:text-white';
export const primaryButton = 'inline-flex items-center gap-2 h-9 px-3 rounded-xl text-sm font-semibold bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-60 transition-colors cursor-pointer';
