import React, { useId, useState } from 'react';
import type { AutonomousOpsTimeSaved } from '../../services/autonomousOpsReporting';
import { InfoIcon } from '../icons';
import {
    ESTIMATE_CHIP, HIDE_MINUTES, MINUTES_HEADERS, MINUTES_TABLE_CAPTION, MINUTES_TOTAL, READOUT_TIME_SAVED, SHOW_MINUTES,
    TIME_SAVED_METHOD, TIME_SAVED_SHADOW_SENTENCE, formatMinutes, plainMinutes,
} from './reportingCopy';

const OUTLINE_CHIP =
    'inline-flex items-center gap-1 rounded-full border border-gray-300 dark:border-gray-600 px-2 py-1 text-xs font-semibold text-gray-700 dark:text-gray-200 break-words';
const TEXT_BUTTON = 'text-sm font-semibold text-gray-900 dark:text-white underline underline-offset-2';
const HEAD = 'px-4 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400';
const NUM = 'px-4 py-2 text-right tabular-nums text-gray-900 dark:text-white';

interface TimeSavedBlockProps {
    timeSaved: AutonomousOpsTimeSaved;
    /** Shadow mode is on: nothing ran, so no time is counted, and the method says so. */
    shadowOnly: boolean;
}

const sum = (rows: AutonomousOpsTimeSaved['perKind']): number => rows.reduce((total, r) => total + (Number.isFinite(r.subtotal) ? r.subtotal : 0), 0);

/**
 * Section 2d: the estimate with its chip, the method (always visible), and a read-only table of the fixed
 * minutes per kind of action as the server supplies it. Nothing here is editable (D-08). Server text renders as React text.
 */
export const TimeSavedBlock: React.FC<TimeSavedBlockProps> = ({ timeSaved, shadowOnly }) => {
    const uid = useId();
    const tableId = `${uid}-minutes`;
    const [open, setOpen] = useState(false);
    const rows = Array.isArray(timeSaved.perKind) ? timeSaved.perKind : [];

    return (
        <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{READOUT_TIME_SAVED}</h3>
                <span className={OUTLINE_CHIP}><InfoIcon size={12} aria-hidden="true" />{ESTIMATE_CHIP}</span>
            </div>
            <p className="break-words text-lg font-semibold tabular-nums text-gray-900 dark:text-white">{formatMinutes(timeSaved.minutes)}</p>
            <p className="max-w-prose break-words text-xs text-gray-500 dark:text-gray-400">{TIME_SAVED_METHOD}</p>
            {shadowOnly && <p className="max-w-prose break-words text-xs text-gray-500 dark:text-gray-400">{TIME_SAVED_SHADOW_SENTENCE}</p>}
            <div>
                <button type="button" aria-expanded={open} aria-controls={tableId} onClick={() => setOpen(v => !v)} className={TEXT_BUTTON}>
                    {open ? HIDE_MINUTES : SHOW_MINUTES}
                </button>
            </div>
            {open && (
                <div id={tableId} className="min-w-0 max-w-full">
                    <table className="w-full table-fixed text-sm sm:table-auto">
                        <caption className="sr-only">{MINUTES_TABLE_CAPTION}</caption>
                        <thead>
                            <tr className="text-left">
                                <th scope="col" className={HEAD}>{MINUTES_HEADERS.kind}</th>
                                <th scope="col" className={`${HEAD} text-right`}>{MINUTES_HEADERS.counted}</th>
                                <th scope="col" className={`${HEAD} text-right`}>{MINUTES_HEADERS.each}</th>
                                <th scope="col" className={`${HEAD} text-right`}>{MINUTES_HEADERS.subtotal}</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200 dark:divide-white/10">
                            {rows.map(r => (
                                <tr key={r.kind}>
                                    <th scope="row" className="break-words px-4 py-2 text-left font-normal text-gray-900 dark:text-white">{r.label}</th>
                                    <td className={NUM}>{r.counted}</td>
                                    <td className={NUM}>{r.minutesEach}</td>
                                    <td className={NUM}>{plainMinutes(r.subtotal)}</td>
                                </tr>
                            ))}
                        </tbody>
                        <tfoot>
                            <tr className="border-t border-gray-200 dark:border-white/10">
                                <th scope="row" className="px-4 py-2 text-left font-semibold text-gray-900 dark:text-white">{MINUTES_TOTAL}</th>
                                <td className={NUM} />
                                <td className={NUM} />
                                <td className={`${NUM} font-semibold`}>{plainMinutes(sum(rows))}</td>
                            </tr>
                        </tfoot>
                    </table>
                </div>
            )}
        </div>
    );
};

export default TimeSavedBlock;
