import React, { useState } from 'react';
import { Workflow } from 'lucide-react';
import { showToast } from '../../../utils/toast';
import { ghostButton } from '../../network/NetworkKit';
import { field, primaryButton, subhead } from './SocKit';
import { RULE_SEVERITIES, huntToRule, ruleBlocker, type HuntCatalogue, type RuleDraft, type RuleSeverity, type SavedHunt } from './huntData';

/** Turn a saved hunt over SIEM events into a SIEM rule: N matching events per count-by value within a window. */
export const HuntRulePanel: React.FC<{
    hunt: SavedHunt; catalogue: HuntCatalogue | null; onClose: () => void; onCreated: (ruleId: string) => void;
}> = ({ hunt, catalogue, onClose, onCreated }) => {
    const [draft, setDraft] = useState<RuleDraft>({ name: hunt.name, severity: 'Medium', count: 5, windowMinutes: 10, alertNow: false });
    const [busy, setBusy] = useState(false);
    const blocker = ruleBlocker(hunt.query);
    const per = hunt.query.countBy || 'agentId';
    const perLabel = catalogue?.sources.events.fields.find(f => f.name === per)?.label ?? per;

    const create = async () => {
        setBusy(true);
        try {
            const rule = await huntToRule(hunt.id, draft);
            showToast(rule.mode === 'record'
                ? `Rule “${rule.name}” created: it records hits for 7 days, then raises alerts`
                : `Rule “${rule.name}” created: it raises alerts from now on`, 'success');
            onCreated(rule.id);
        } catch (e) {
            showToast(e instanceof Error ? e.message : 'The rule was not created', 'error');
        } finally {
            setBusy(false);
        }
    };

    return (
        <section aria-label="Make a SIEM rule" className="rounded-xl border border-gray-200/80 dark:border-white/[0.08] p-4 space-y-3">
            <h4 className={`${subhead} flex items-center gap-1.5`}><Workflow className="w-3.5 h-3.5" aria-hidden="true" />Make a SIEM rule from “{hunt.name}”</h4>
            {blocker ? <p role="alert" className="text-sm text-amber-800 dark:text-amber-200">{blocker}</p> : (
                <>
                    <div className="flex flex-wrap items-end gap-3">
                        <label><span className="block text-[11px] text-gray-500 dark:text-gray-400">Rule name</span>
                            <input value={draft.name} maxLength={120} onChange={e => setDraft(d => ({ ...d, name: e.target.value }))} className={`${field} w-64 px-3`} /></label>
                        <label><span className="block text-[11px] text-gray-500 dark:text-gray-400">Severity</span>
                            <select value={draft.severity} onChange={e => setDraft(d => ({ ...d, severity: e.target.value as RuleSeverity }))} className={`${field} px-2`}>
                                {RULE_SEVERITIES.map(s => <option key={s} value={s}>{s}</option>)}</select></label>
                        <label><span className="block text-[11px] text-gray-500 dark:text-gray-400">At least</span>
                            <input type="number" min={1} max={1000} value={draft.count} onChange={e => setDraft(d => ({ ...d, count: Math.max(1, Math.min(1000, Number(e.target.value) || 1)) }))} className={`${field} w-24 px-3`} /></label>
                        <label><span className="block text-[11px] text-gray-500 dark:text-gray-400">Within (minutes)</span>
                            <input type="number" min={1} max={1440} value={draft.windowMinutes} onChange={e => setDraft(d => ({ ...d, windowMinutes: Math.max(1, Math.min(1440, Number(e.target.value) || 1)) }))} className={`${field} w-24 px-3`} /></label>
                    </div>
                    <p className="text-sm text-gray-700 dark:text-gray-300">
                        Fires when {draft.count} or more matching events share one {perLabel} within {draft.windowMinutes} minute{draft.windowMinutes === 1 ? '' : 's'}.
                        {hunt.query.countBy ? '' : ' Set “Count by” on the hunt to group by something other than the endpoint.'}
                    </p>
                    <label className="inline-flex items-center gap-1.5 text-sm text-gray-800 dark:text-gray-200 cursor-pointer">
                        <input type="checkbox" checked={draft.alertNow} onChange={e => setDraft(d => ({ ...d, alertNow: e.target.checked }))} />
                        Raise alerts at once (otherwise it records hits for 7 days first, so a noisy rule can be tuned)
                    </label>
                </>
            )}
            <div className="flex flex-wrap gap-2">
                {!blocker && <button type="button" className={primaryButton} disabled={busy || !draft.name.trim()} onClick={create}>Create rule</button>}
                <button type="button" className={ghostButton} onClick={onClose}>Cancel</button>
            </div>
        </section>
    );
};
