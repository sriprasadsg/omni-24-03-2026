import React, { useId, useState } from 'react';
import { OnOffSwitch } from '../AutonomousOpsResponseSettings';
import { FileTextIcon, LockIcon, PencilIcon, SparklesIcon } from '../icons';
import { showToast } from '../../utils/toast';
import { patchArticle } from '../../services/serviceDesk/knowledgeApi';
import { DeskChip, ERROR_LINE, MUTED, SECONDARY_BUTTON, failureLine } from './deskUi';
import { KB, fill } from './serviceDeskCopy';

/**
 * The Help desk mark of one article on the Knowledge Base screen (UI-SPEC section 6, D-16, D-17): the chips a row wears and
 * the switch that decides whether the service desk may quote it. The server decides who may switch (the screen passes these
 * parts only when `canManageArticles` is true) and refuses a shared (platform) article, so the screen never shows a switch for one.
 */

/** Help desk (BLUE), Starter copy (OUTLINE) and Platform reference (OUTLINE with a lock): a wrapping row of chips. */
export const HelpDeskChips: React.FC<{ helpdesk: boolean; starter: boolean; platform: boolean }> = ({ helpdesk, starter, platform }) => {
    if (!helpdesk && !starter && !platform) return null;
    return (
        <div className="flex flex-wrap gap-2">
            {helpdesk && <DeskChip tone="blue" icon={SparklesIcon}>{KB.chipHelpDesk}</DeskChip>}
            {starter && <DeskChip tone="outline" icon={FileTextIcon}>{KB.chipStarterCopy}</DeskChip>}
            {platform && <DeskChip tone="outline" icon={LockIcon}>{KB.chipPlatformReference}</DeskChip>}
        </div>
    );
};

/** The muted line a shared (platform) article shows in place of the switch. */
export const SharedReferenceLine: React.FC = () => <p className={MUTED}>{KB.sharedReference}</p>;

/**
 * The Help desk switch. It saves immediately and is not optimistic: it keeps showing the stored value and is disabled while
 * the request runs, so one press sends one request; a failure leaves it as it was and says why under it. The visible words
 * are On and Off, and the accessible name carries the article title.
 */
export const HelpDeskToggle: React.FC<{
    docId: string;
    title: string;
    checked: boolean;
    /** Called with the new value once the server has saved it. */
    onChanged: (next: boolean) => void;
}> = ({ docId, title, checked, onChanged }) => {
    const labelId = useId();
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);

    async function change(next: boolean) {
        if (pending) return;
        setPending(true);
        setError(null);
        try {
            await patchArticle(docId, { helpdesk: next });
            showToast(fill(next ? KB.toggleOn : KB.toggleOff, { title }), 'success');
            onChanged(next);
        } catch (e) {
            setError(failureLine(e, KB.toggleFailed, KB.toggleFailedFallback));
        } finally {
            setPending(false);
        }
    }

    return (
        <div className="flex flex-col items-end gap-1">
            <span id={labelId} className="sr-only">{fill(KB.switchAria, { title })}</span>
            <OnOffSwitch
                checked={checked}
                labelledBy={labelId}
                disabled={pending}
                stateText={checked ? KB.switchOn : KB.switchOff}
                onChange={change}
            />
            {error && <p role="alert" className={`${ERROR_LINE} text-right`}>{error}</p>}
        </div>
    );
};

/** Edit article: a secondary button that opens the article dialog for this row. */
export const EditArticleButton: React.FC<{ title: string; onEdit: () => void }> = ({ title, onEdit }) => (
    <button type="button" className={SECONDARY_BUTTON} onClick={onEdit} aria-label={`${KB.editArticle}: ${title}`}>
        <PencilIcon size={16} aria-hidden="true" />
        {KB.editArticle}
    </button>
);
