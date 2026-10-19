import React, { useCallback, useEffect, useState } from 'react';
import { LayoutGrid } from 'lucide-react';
import { Modal } from './Modal';

/** Overview widgets a user can hide. The role's gates still apply first: hiding never grants. */
export const OVERVIEW_WIDGETS = [
    { id: 'metrics', label: 'Key metrics', hint: 'CPU, memory, disk and security event tiles' },
    { id: 'health', label: 'System health chart', hint: 'Last 30 minutes of CPU, disk and memory' },
    { id: 'alerts', label: 'Recent signals', hint: 'Latest alerts' },
    { id: 'insights', label: 'AI insights', hint: 'AI-driven health analysis' },
    { id: 'kpi', label: 'Business KPIs', hint: 'Business KPI correlation chart' },
    { id: 'aiHealth', label: 'AI system health', hint: 'Active and inactive AI systems' },
    { id: 'compliance', label: 'Compliance', hint: 'Compliance score and framework status' },
] as const;

export type OverviewWidgetId = typeof OVERVIEW_WIDGETS[number]['id'];

const storageKey = (userKey: string) => `omni.overview.hidden.${userKey}`;

/** Widgets this user hid, kept per user in this browser (a convenience: storage may be unavailable). */
export function useOverviewHidden(userKey: string | null) {
    const read = useCallback((): OverviewWidgetId[] => {
        if (!userKey) return [];
        try {
            const parsed = JSON.parse(localStorage.getItem(storageKey(userKey)) ?? '[]');
            const known = new Set<string>(OVERVIEW_WIDGETS.map(w => w.id));
            return Array.isArray(parsed) ? parsed.filter((id): id is OverviewWidgetId => known.has(id)) : [];
        } catch {
            return [];
        }
    }, [userKey]);
    const [hidden, setHidden] = useState<OverviewWidgetId[]>(read);
    useEffect(() => { setHidden(read()); }, [read]);

    const save = useCallback((next: OverviewWidgetId[]) => {
        setHidden(next);
        if (!userKey) return;
        try { localStorage.setItem(storageKey(userKey), JSON.stringify(next)); } catch { /* session-only */ }
    }, [userKey]);

    return { hidden, setHidden: save };
}

interface OverviewCustomizerProps {
    isOpen: boolean;
    onClose: () => void;
    /** Widgets the role may see; only these are listed. */
    available: OverviewWidgetId[];
    hidden: OverviewWidgetId[];
    onChange: (hidden: OverviewWidgetId[]) => void;
}

export const OverviewCustomizer: React.FC<OverviewCustomizerProps> = ({ isOpen, onClose, available, hidden, onChange }) => {
    const widgets = OVERVIEW_WIDGETS.filter(w => available.includes(w.id));
    const toggle = (id: OverviewWidgetId) =>
        onChange(hidden.includes(id) ? hidden.filter(h => h !== id) : [...hidden, id]);

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title="Customize Overview"
            icon={<LayoutGrid className="h-5 w-5 text-primary-500" />}
            size="md"
            footer={
                <div className="flex items-center justify-between w-full gap-3">
                    <button
                        onClick={() => onChange([])}
                        disabled={hidden.length === 0}
                        className="h-9 px-3 rounded-xl text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-900/[0.05] dark:hover:bg-white/[0.07] disabled:opacity-40 transition-colors"
                    >
                        Show all
                    </button>
                    <button onClick={onClose} className="h-9 px-4 rounded-xl text-sm font-semibold text-white bg-primary-600 hover:bg-primary-700 transition-colors">
                        Done
                    </button>
                </div>
            }
        >
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">Choose what your Overview shows. This only changes your view, in this browser.</p>
            <ul className="divide-y divide-gray-100 dark:divide-white/[0.06]">
                {widgets.map(w => {
                    const on = !hidden.includes(w.id);
                    return (
                        <li key={w.id} className="flex items-center justify-between gap-4 py-3">
                            <div className="min-w-0">
                                <p className="text-sm font-medium text-gray-900 dark:text-white">{w.label}</p>
                                <p className="text-xs text-gray-500 dark:text-gray-400">{w.hint}</p>
                            </div>
                            <button
                                role="switch"
                                aria-checked={on}
                                aria-label={`Show ${w.label}`}
                                onClick={() => toggle(w.id)}
                                className={`relative flex-shrink-0 h-6 w-11 rounded-full transition-colors ${on ? 'bg-primary-600' : 'bg-gray-300 dark:bg-white/15'}`}
                            >
                                <span className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${on ? 'translate-x-5' : ''}`} />
                            </button>
                        </li>
                    );
                })}
            </ul>
        </Modal>
    );
};
