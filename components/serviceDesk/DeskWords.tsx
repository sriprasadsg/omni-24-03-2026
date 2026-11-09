import React, { useId, useState } from 'react';
import { SECONDARY_BUTTON } from '../AutonomousOpsHealthCards';
import { PlusIcon, XIcon } from '../icons';
import { VALIDATION, WORDS, fill } from './serviceDeskCopy';

const HELPER = 'break-words text-xs text-gray-500 dark:text-gray-400';
const FIELD =
    'min-h-10 rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-900 disabled:opacity-60 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100';

export const MAX_WORDS = 50;
const MIN_LENGTH = 2;
const MAX_LENGTH = 40;
/** Letters and digits of any script, space, hyphen, apostrophe, ampersand, slash and dot: the server's rule (85-11). */
const ALLOWED = /^[\p{L}\p{N} '\-&/.]+$/u;

/** A typed word the way the server stores it: trimmed, inner spaces collapsed, lower case. */
export const normalizeWord = (raw: string): string => raw.trim().replace(/\s+/g, ' ').toLowerCase();

/** The sentence that refuses a typed word, or null when it may be added. The server still decides. */
export function wordProblem(raw: string, list: string[], max: number = MAX_WORDS): string | null {
    const word = normalizeWord(raw);
    if (!word) return VALIDATION.wordEmpty;
    if (word.length < MIN_LENGTH || word.length > MAX_LENGTH || !ALLOWED.test(word)) return VALIDATION.wordShape;
    if (list.includes(word)) return fill(VALIDATION.wordDuplicate, { word });
    if (list.length >= max) return VALIDATION.wordLimit;
    return null;
}

interface WordsProps {
    words: string[];
    onChange: (next: string[]) => void;
    disabled?: boolean;
    max?: number;
}

/**
 * The tenant's own hand-off words (UI-SPEC 2e): a field, wrapping chips, a counter and the built-in rules. Words stay
 * staged until the card's single Save.
 */
export const DeskWords: React.FC<WordsProps> = ({ words, onChange, disabled, max = MAX_WORDS }) => {
    const uid = useId();
    const labelId = `${uid}-label`;
    const errorId = `${uid}-error`;
    const rulesId = `${uid}-rules`;
    const [input, setInput] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [rulesOpen, setRulesOpen] = useState(false);

    const tryAdd = () => {
        const problem = wordProblem(input, words, max);
        if (problem) { setError(problem); return; }
        onChange([...words, normalizeWord(input)]);
        setInput('');
        setError(null);
    };

    return (
        <div className="flex flex-col gap-2">
            <p id={labelId} className="break-words text-sm font-semibold text-gray-900 dark:text-white">{WORDS.label}</p>
            <p className={HELPER}>{WORDS.helper}</p>
            <div className="flex items-start gap-2">
                <input
                    type="text" aria-label={WORDS.inputLabel} placeholder={WORDS.placeholder} value={input} disabled={disabled}
                    aria-invalid={error !== null} aria-describedby={error ? errorId : undefined}
                    onChange={e => { setInput(e.target.value); setError(null); }}
                    onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); tryAdd(); } }}
                    className={`${FIELD} w-full max-w-sm`}
                />
                <button type="button" className={SECONDARY_BUTTON} disabled={disabled} onClick={tryAdd}>
                    <PlusIcon size={16} aria-hidden="true" />
                    {WORDS.add}
                </button>
            </div>
            {error && <p id={errorId} role="alert" className="break-words text-xs text-red-600 dark:text-red-400">{error}</p>}
            {words.length === 0 ? (
                <p className={HELPER}>{WORDS.empty}</p>
            ) : (
                <ul className="flex flex-wrap gap-2" aria-label={WORDS.listLabel}>
                    {words.map(word => (
                        <li key={word} className="inline-flex max-w-full items-center gap-1 rounded-full border border-gray-300 pl-3 pr-1 text-xs dark:border-gray-600">
                            <span className="min-w-0 break-words font-normal text-gray-900 dark:text-gray-100">{word}</span>
                            <button
                                type="button" aria-label={fill(WORDS.remove, { word })} disabled={disabled}
                                onClick={() => onChange(words.filter(w => w !== word))}
                                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-white/10"
                            >
                                <XIcon size={16} aria-hidden="true" />
                            </button>
                        </li>
                    ))}
                </ul>
            )}
            <p className={`tabular-nums ${HELPER}`}>{fill(WORDS.counter, { n: words.length })}</p>
            <div>
                <button
                    type="button" aria-expanded={rulesOpen} aria-controls={rulesId} onClick={() => setRulesOpen(v => !v)}
                    className="min-h-10 text-sm font-semibold text-gray-900 underline underline-offset-2 dark:text-white"
                >
                    {rulesOpen ? WORDS.hideRules : WORDS.showRules}
                </button>
                {rulesOpen && (
                    <ul id={rulesId} className="mt-2 flex list-disc flex-col gap-1 pl-4">
                        {WORDS.builtIn.map(line => <li key={line} className={HELPER}>{line}</li>)}
                    </ul>
                )}
            </div>
        </div>
    );
};
