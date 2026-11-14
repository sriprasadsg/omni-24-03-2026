import React, { useEffect, useId, useState } from 'react';
import type { AutonomousOpsRuleStats, AutonomousOpsStatsTotals } from '../../services/autonomousOpsReporting';
import { FlaskConicalIcon } from '../icons';
import {
    ALL_RULES, GLOSSARY, GLOSSARY_HIDE, GLOSSARY_SHOW, MISSING_COUNT, RULES_VISIBLE, RULE_COUNT_COLUMNS, RULE_HEADER,
    SHOW_FEWER_RULES, SIMULATION_HEADER, rulesCaption, showAllRules, simulationCard,
} from './reportingCopy';

type CountKey = (typeof RULE_COUNT_COLUMNS)[number]['key'];
type Counts = Partial<Record<CountKey | 'wouldHaveDone', unknown>>;

const SIM_RULE = 'border-l-2 border-dashed border-gray-400 dark:border-gray-500';
const TEXT_BUTTON = 'text-sm font-semibold text-gray-900 dark:text-white underline underline-offset-2';
const MUTED = 'text-gray-500 dark:text-gray-400';
const HEAD = 'px-4 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400';
const WIDE_QUERY = '(min-width: 1024px)';

/** lg and wider shows the table; below it the cards. With no matchMedia (tests, old engines) the wide layout is used. */
function useWideLayout(): boolean {
    const read = () => (typeof window !== 'undefined' && typeof window.matchMedia === 'function' ? window.matchMedia(WIDE_QUERY).matches : true);
    const [wide, setWide] = useState(read);
    useEffect(() => {
        if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
        const list = window.matchMedia(WIDE_QUERY);
        const onChange = () => setWide(list.matches);
        list.addEventListener?.('change', onChange);
        return () => list.removeEventListener?.('change', onChange);
    }, []);
    return wide;
}

/** A count the server did not send is a dash, never a zero: the row still renders. */
const count = (value: unknown): number | null => (typeof value === 'number' && Number.isFinite(value) ? value : null);
const show = (value: unknown): string => { const n = count(value); return n === null ? MISSING_COUNT : String(n); };
const tone = (value: unknown): string => (count(value) === null || count(value) === 0 ? MUTED : 'text-gray-900 dark:text-white');

/** Fired descending, then name, then id. The server already sends this order; it is repeated here so a stale order never shows. */
function sortRules(rules: AutonomousOpsRuleStats[]): AutonomousOpsRuleStats[] {
    return [...rules].sort((a, b) =>
        (count(b.fired) ?? 0) - (count(a.fired) ?? 0) || a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
}

const RuleName: React.FC<{ rule: AutonomousOpsRuleStats }> = ({ rule }) => (
    <>
        <div className="break-words text-sm font-semibold text-gray-900 dark:text-white">{rule.name}</div>
        <div className={`break-all font-mono text-xs font-normal ${MUTED}`}>{rule.id}</div>
    </>
);

const RuleTable: React.FC<{ rules: AutonomousOpsRuleStats[]; totals: Counts; days: number }> = ({ rules, totals, days }) => (
    <div role="region" aria-label={rulesCaption(days)} tabIndex={0} className="min-w-0 overflow-x-auto">
        <table className="w-full min-w-0 text-sm">
            <caption className="sr-only">{rulesCaption(days)}</caption>
            <thead>
                <tr className="text-left">
                    <th scope="col" className={`${HEAD} min-w-[240px]`}>{RULE_HEADER}</th>
                    {RULE_COUNT_COLUMNS.map(c => <th key={c.key} scope="col" className={`${HEAD} min-w-[72px] text-right`}>{c.label}</th>)}
                    <th scope="col" className={`${HEAD} min-w-[144px] text-right ${SIM_RULE}`}>
                        <span className="inline-flex items-center justify-end gap-1">
                            <FlaskConicalIcon size={12} aria-hidden="true" />
                            {SIMULATION_HEADER}
                        </span>
                    </th>
                </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-white/10">
                {rules.map(rule => (
                    <tr key={rule.id}>
                        <th scope="row" className="px-4 py-2 text-left align-top font-normal"><RuleName rule={rule} /></th>
                        {RULE_COUNT_COLUMNS.map(c => (
                            <td key={c.key} className={`px-4 py-2 text-right align-top tabular-nums ${tone(rule[c.key])}`}>{show(rule[c.key])}</td>
                        ))}
                        <td className={`px-4 py-2 text-right align-top tabular-nums ${MUTED} ${SIM_RULE}`}>{show(rule.wouldHaveDone)}</td>
                    </tr>
                ))}
            </tbody>
            <tfoot>
                <tr className="border-t border-gray-200 dark:border-white/10">
                    <th scope="row" className="px-4 py-2 text-left text-sm font-semibold text-gray-900 dark:text-white">{ALL_RULES}</th>
                    {RULE_COUNT_COLUMNS.map(c => (
                        <td key={c.key} className={`px-4 py-2 text-right font-semibold tabular-nums ${tone(totals[c.key])}`}>{show(totals[c.key])}</td>
                    ))}
                    <td className={`px-4 py-2 text-right tabular-nums ${MUTED} ${SIM_RULE}`}>{show(totals.wouldHaveDone)}</td>
                </tr>
            </tfoot>
        </table>
    </div>
);

const RuleCards: React.FC<{ rules: AutonomousOpsRuleStats[] }> = ({ rules }) => (
    <ul className="divide-y divide-gray-200 dark:divide-white/10">
        {rules.map(rule => (
            <li key={rule.id} className="p-4">
                <RuleName rule={rule} />
                <dl className="mt-4 grid grid-cols-2 gap-2">
                    {RULE_COUNT_COLUMNS.map(c => (
                        <div key={c.key} className="min-w-0">
                            <dt className={`text-xs ${MUTED}`}>{c.label}</dt>
                            <dd className={`text-sm tabular-nums ${tone(rule[c.key])}`}>{show(rule[c.key])}</dd>
                        </div>
                    ))}
                </dl>
                <p className="mt-4 break-words border-t border-dashed border-gray-400 pt-4 text-sm text-gray-600 dark:border-gray-500 dark:text-gray-400">
                    {simulationCard(show(rule.wouldHaveDone))}
                </p>
            </li>
        ))}
    </ul>
);

const Glossary: React.FC = () => {
    const uid = useId();
    const [open, setOpen] = useState(false);
    return (
        <div>
            <button type="button" aria-expanded={open} aria-controls={`${uid}-glossary`} onClick={() => setOpen(v => !v)} className={TEXT_BUTTON}>
                {open ? GLOSSARY_HIDE : GLOSSARY_SHOW}
            </button>
            {open && (
                <dl id={`${uid}-glossary`} className={`mt-2 flex flex-col gap-1 text-xs ${MUTED}`}>
                    {GLOSSARY.map(g => (
                        <div key={g.term} className="flex flex-wrap gap-x-1">
                            <dt className="font-semibold text-gray-700 dark:text-gray-200">{g.term}</dt>
                            <dd className="break-words">{g.meaning}</dd>
                        </div>
                    ))}
                </dl>
            )}
        </div>
    );
};

interface StatsRuleTableProps {
    rules: AutonomousOpsRuleStats[];
    totals: AutonomousOpsStatsTotals;
    days: number;
}

/**
 * Section 2e: decisions by rule. A real table at lg and wider, stacked cards below; when the card is narrower than the
 * table (about 946 px) the table scrolls sideways inside the card (G-86-5).
 * The "Would have done (simulation)" column is set apart by a dashed rule so a simulation is never read as a real count (ACTV-05).
 * Also a totals row, show-all past 15 rules and a glossary of every column. Rule names and ids are server text
 * and render as React text only.
 */
export const StatsRuleTable: React.FC<StatsRuleTableProps> = ({ rules, totals, days }) => {
    const wide = useWideLayout();
    const [all, setAll] = useState(false);
    const sorted = sortRules(rules);
    const visible = all ? sorted : sorted.slice(0, RULES_VISIBLE);
    return (
        <div className="flex flex-col gap-4">
            <div className="min-w-0">
                {wide ? <RuleTable rules={visible} totals={totals} days={days} /> : <RuleCards rules={visible} />}
            </div>
            {sorted.length > RULES_VISIBLE && (
                <div>
                    <button type="button" onClick={() => setAll(v => !v)} className={TEXT_BUTTON}>
                        {all ? SHOW_FEWER_RULES : showAllRules(sorted.length)}
                    </button>
                </div>
            )}
            <Glossary />
        </div>
    );
};

export default StatsRuleTable;
