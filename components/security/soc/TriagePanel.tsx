import React, { useState } from 'react';
import { Loader2, Sparkles } from 'lucide-react';
import { authFetch } from '../../../services/apiService';
import { ghostButton } from '../../network/NetworkKit';
import { STEP_LABEL, formatWhen, triageAlert, type AiTriage, type Severity, type TriageStep } from './socData';
import { SeverityBadge, subhead } from './SocKit';

/**
 * "Explain this alert": the platform's local AI model reads a trimmed copy of the alert and answers with a
 * summary, likely cause, seriousness and next steps. Advice only: a step points at the console's own
 * control, it never runs anything.
 */
export const TriagePanel: React.FC<{ alertId: string; triage: AiTriage | null | undefined; canRun: boolean;
    onTriaged: (t: AiTriage) => void; onStep: (step: TriageStep) => void; runner?: () => Promise<AiTriage>; askLabel?: string }> = ({ alertId, triage, canRun, onTriaged, onStep, runner, askLabel = 'Explain this alert' }) => {
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const run = async () => {
        setBusy(true);
        setError(null);
        try {
            onTriaged(await (runner ? runner() : triageAlert(authFetch, alertId)));
        } catch (e) {
            setError(e instanceof Error ? e.message : 'The AI explanation failed');
        } finally {
            setBusy(false);
        }
    };

    return (
        <section aria-labelledby={`triage-${alertId}`} className="rounded-xl border border-primary-500/25 bg-primary-500/[0.04] p-3">
            <div className="flex items-center justify-between gap-2">
                <h3 id={`triage-${alertId}`} className={`${subhead} flex items-center gap-1.5`}>
                    <Sparkles className="w-3.5 h-3.5 text-primary-600 dark:text-primary-400" aria-hidden="true" />AI triage
                </h3>
                {canRun && (
                    <button type="button" className={`${ghostButton} h-8`} disabled={busy} onClick={run}>
                        {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />}
                        {triage ? 'Ask again' : askLabel}
                    </button>
                )}
            </div>
            <div aria-live="polite">
                {busy && <p className="mt-2 text-xs text-gray-600 dark:text-gray-300">The local AI model is reading the alert; this takes up to a minute.</p>}
                {error && <p role="alert" className="mt-2 text-xs text-red-700 dark:text-red-300">{error}</p>}
            </div>
            {triage ? (
                <div className="mt-2 space-y-2 text-[13px] text-gray-800 dark:text-gray-200">
                    <p>{triage.summary}</p>
                    {triage.likelyCause && <p><span className="font-medium">Likely cause: </span>{triage.likelyCause}</p>}
                    {triage.seriousness && (
                        <p className="flex flex-wrap items-center gap-2"><span className="font-medium">Seriousness:</span>
                            <SeverityBadge severity={triage.seriousness as Severity} />
                            {triage.why && <span className="basis-full text-xs text-gray-600 dark:text-gray-300">{triage.why}</span>}
                        </p>
                    )}
                    {triage.nextSteps.length > 0 && (
                        <div>
                            <p className="font-medium">Suggested next steps</p>
                            <ul className="mt-1 flex flex-wrap gap-1.5">
                                {triage.nextSteps.map(step => (
                                    <li key={step}>
                                        <button type="button" onClick={() => onStep(step)}
                                            className="rounded-lg px-2 py-1 text-xs font-medium bg-white dark:bg-white/[0.06] border border-gray-200/80 dark:border-white/[0.08] text-primary-700 dark:text-primary-300 hover:border-primary-500/50">
                                            {STEP_LABEL[step]}
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                    <p className="text-[11px] text-gray-500 dark:text-gray-400">
                        AI suggestion: check it before acting. {triage.model} on this server, {formatWhen(triage.at)}
                        {triage.by.startsWith('automatic') ? ', made automatically for a critical alert' : ''}.
                    </p>
                </div>
            ) : !busy && (
                <p className="mt-2 text-xs text-gray-600 dark:text-gray-300">
                    {canRun ? 'Ask the platform\'s own AI model what this alert means and what to do. Nothing leaves this server.' : 'No AI explanation yet.'}
                </p>
            )}
        </section>
    );
};
