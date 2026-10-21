import React, { useId } from 'react';

const TILE_TONES = {
    primary: 'text-primary-600 dark:text-primary-400 bg-primary-500/10 ring-primary-500/20',
    blue: 'text-blue-600 dark:text-blue-400 bg-blue-500/10 ring-blue-500/20',
    red: 'text-red-600 dark:text-red-400 bg-red-500/10 ring-red-500/20',
    orange: 'text-orange-600 dark:text-orange-400 bg-orange-500/10 ring-orange-500/20',
    amber: 'text-amber-600 dark:text-amber-400 bg-amber-500/10 ring-amber-500/20',
};

export const bigNumber = 'text-[32px] leading-none font-semibold tracking-[-0.03em] tabular-nums';

// Spatial Glass stat tile, the same anatomy as the Overview KPI tiles minus the sparkline
// (there is no history behind these counts). A labelled group, so the value is read with its label.
export const StatTile: React.FC<{ icon: React.ReactNode; label: string; tone: keyof typeof TILE_TONES; footnote?: React.ReactNode; children: React.ReactNode }> = ({ icon, label, tone, footnote, children }) => {
    const labelId = useId();
    return (
        <div role="group" aria-labelledby={labelId} className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card p-5 flex flex-col">
            <div className="flex items-center gap-3 min-w-0">
                <span className={`grid place-items-center h-9 w-9 flex-shrink-0 rounded-xl ring-1 ring-inset ${TILE_TONES[tone]}`}>{icon}</span>
                <p id={labelId} className="text-[13px] font-medium text-gray-600 dark:text-gray-400 truncate">{label}</p>
            </div>
            <div className="mt-3">{children}</div>
            {footnote && <p className="mt-auto pt-2 text-xs text-gray-500 dark:text-gray-400">{footnote}</p>}
        </div>
    );
};
