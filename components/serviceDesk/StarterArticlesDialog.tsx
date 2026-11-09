import React, { useState } from 'react';
import { Modal } from '../Modal';
import { showToast } from '../../utils/toast';
import { addStarters } from '../../services/serviceDesk/knowledgeApi';
import type { StarterResult } from '../../services/serviceDesk/types';
import { ACCENT_BUTTON, HealthNotice, SECONDARY_BUTTON, failureLine } from './deskUi';
import { DIALOGS, KB, TOASTS, fill } from './serviceDeskCopy';

/** The toast for what the press did: how many were added (singular, plural) or that nothing was missing. */
export function startersToast(result: StarterResult): string {
    if (result.added <= 0) return TOASTS.startersNone;
    return result.added === 1 ? TOASTS.startersAddedOne : fill(TOASTS.startersAdded, { n: result.added });
}

/**
 * Add starter IT articles? (UI-SPEC section 6, D-28, DESK-07). It writes articles into the knowledge base, so it asks first.
 * Close without adding takes first focus. The articles are editable copies marked Help desk; pressing it again adds nothing
 * twice, and `missing` says how many are still to add. Neither the buttons nor Esc close it while the request runs.
 */
export const StarterArticlesDialog: React.FC<{
    missing: number;
    onClose: () => void;
    /** Called after the server answered, so the screen reads its list and flags again. */
    onDone: (result: StarterResult) => void;
}> = ({ missing, onClose, onDone }) => {
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);

    async function add() {
        if (pending) return;
        setPending(true);
        setError(null);
        try {
            const result = await addStarters();
            showToast(startersToast(result), 'success');
            onDone(result);
        } catch (e) {
            setError(failureLine(e, KB.starterFailed, KB.starterFailedFallback));
        } finally {
            setPending(false);
        }
    }

    return (
        <Modal
            isOpen
            onClose={onClose}
            title={DIALOGS.starters.title}
            size="md"
            showClose={false}
            closeOnBackdrop={false}
            closeOnEsc={!pending}
            footer={(
                <>
                    <button type="button" className={SECONDARY_BUTTON} onClick={onClose} disabled={pending}>{DIALOGS.starters.keep}</button>
                    <button type="button" className={ACCENT_BUTTON} onClick={add} disabled={pending}>
                        {pending ? DIALOGS.starters.pending : DIALOGS.starters.confirm}
                    </button>
                </>
            )}
        >
            <div className="flex flex-col gap-4">
                <p className="break-words text-sm text-gray-700 dark:text-gray-200">{fill(DIALOGS.starters.body, { n: missing })}</p>
                {error && <HealthNotice tone="red" role="alert"><p>{error}</p></HealthNotice>}
            </div>
        </Modal>
    );
};
