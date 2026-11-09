import React, { useEffect, useId, useState } from 'react';
import { Modal } from '../Modal';
import { FIELD } from '../AutonomousOpsResponseSettings';
import { showToast } from '../../utils/toast';
import { DEFAULT_ARTICLE_MAX, createArticle, fetchArticle, patchArticle } from '../../services/serviceDesk/knowledgeApi';
import { ERROR_LINE, HealthNotice, MUTED, SECONDARY_BUTTON, TEXT_BUTTON, failureLine } from './deskUi';
import { KB, TOASTS, VALIDATION, fill } from './serviceDeskCopy';

/** The article of a row the dialog edits (the parts the list already carries; the text is read from the server). */
export interface EditableArticle {
    id: string;
    title: string;
    tags: string[];
    starterKey?: string | null;
}

export interface ArticleEditDialogProps {
    mode: 'edit' | 'write';
    /** Edit: the article to change. */
    doc?: EditableArticle;
    /** Write: the title to start from (the question of a knowledge gap). */
    initialTitle?: string;
    /** Write: the knowledge-gap group this article answers; saving closes the gap. */
    gapGroupId?: string;
    onClose: () => void;
    /** Called once the article is saved, so the screen reads its list again. */
    onSaved: () => void;
}

const TITLE_MAX = 200;

/** "it, printer" becomes ['it', 'printer']; empty parts are dropped. */
const splitTags = (text: string): string[] => text.split(',').map(t => t.trim()).filter(Boolean);
const sameTags = (a: string[], b: string[]) => a.length === b.length && a.every((t, i) => t === b[i]);

interface Stored { title: string; content: string; tags: string[]; helpdesk: boolean }

/**
 * Edit article / Write article (UI-SPEC section 6). Edit reads the stored text first (the list leaves it out) and sends only
 * what changed; Write starts a new article, from a knowledge gap with the question as its title and the Help desk mark ticked,
 * and saving closes that gap. Save article stays a secondary button so the accent list stays small. The dialog closes only
 * through its own buttons (nothing is lost to a stray click), and not at all while a request runs.
 */
export const ArticleEditDialog: React.FC<ArticleEditDialogProps> = ({ mode, doc, initialTitle, gapGroupId, onClose, onSaved }) => {
    const ids = { title: useId(), content: useId(), tags: useId(), count: useId(), help: useId() };
    const editing = mode === 'edit';
    const [load, setLoad] = useState<'loading' | 'ready' | 'failed'>(editing ? 'loading' : 'ready');
    const [attempt, setAttempt] = useState(0);
    const [stored, setStored] = useState<Stored | null>(null);
    const [title, setTitle] = useState(editing ? (doc?.title ?? '') : (initialTitle ?? ''));
    const [content, setContent] = useState('');
    const [tags, setTags] = useState(editing ? (doc?.tags ?? []).join(', ') : '');
    const [helpdesk, setHelpdesk] = useState(!editing);
    const [max, setMax] = useState(DEFAULT_ARTICLE_MAX);
    const [errors, setErrors] = useState<{ title?: string; content?: string }>({});
    const [pending, setPending] = useState(false);
    const [saveError, setSaveError] = useState<string | null>(null);

    useEffect(() => {
        if (!editing || !doc) return undefined;
        let cancelled = false;
        setLoad('loading');
        fetchArticle(doc.id).then(detail => {
            if (cancelled) return;
            const text = typeof detail.content === 'string' ? detail.content : '';
            setStored({ title: detail.title, content: text.trim(), tags: detail.tags ?? [], helpdesk: detail.helpdesk === true });
            setTitle(detail.title);
            setContent(text);
            setTags((detail.tags ?? []).join(', '));
            setHelpdesk(detail.helpdesk === true);
            setMax(typeof detail.max === 'number' && detail.max > 0 ? detail.max : DEFAULT_ARTICLE_MAX);
            setLoad('ready');
        }).catch(() => { if (!cancelled) setLoad('failed'); });
        return () => { cancelled = true; };
    }, [editing, doc?.id, attempt]);

    const tagList = splitTags(tags);
    const over = content.trim().length > max;
    const contentError = errors.content ?? (over ? fill(VALIDATION.contentTooLong, { max }) : undefined);
    const dirty = !editing || !stored || title.trim() !== stored.title || content.trim() !== stored.content
        || !sameTags(tagList, stored.tags) || helpdesk !== stored.helpdesk;
    const busy = pending || load !== 'ready';
    const starterCopy = editing && !!doc?.starterKey;

    async function save() {
        const t = title.trim();
        const c = content.trim();
        const found = {
            title: t ? undefined : VALIDATION.titleEmpty,
            content: !c ? VALIDATION.contentEmpty : c.length > max ? fill(VALIDATION.contentTooLong, { max }) : undefined,
        };
        setErrors(found);
        if (found.title || found.content || pending) return;
        setPending(true);
        setSaveError(null);
        try {
            if (editing && doc && stored) {
                await patchArticle(doc.id, {
                    ...(t !== stored.title ? { title: t } : {}),
                    ...(c !== stored.content ? { content: c } : {}),
                    ...(!sameTags(tagList, stored.tags) ? { tags: tagList } : {}),
                    ...(helpdesk !== stored.helpdesk ? { helpdesk } : {}),
                });
            } else {
                await createArticle({ title: t, content: c, tags: tagList, helpdesk, ...(gapGroupId ? { gapGroupId } : {}) });
            }
            showToast(gapGroupId ? TOASTS.articleSavedGap : TOASTS.articleSaved, 'success');
            onSaved();
        } catch (e) {
            setSaveError(failureLine(e, KB.saveFailed, KB.saveFailedFallback));
        } finally {
            setPending(false);
        }
    }

    return (
        <Modal
            isOpen
            onClose={onClose}
            title={editing ? KB.articleDialogEdit : KB.articleDialogWrite}
            size="2xl"
            showClose={false}
            closeOnBackdrop={false}
            closeOnEsc={!pending}
            footer={(
                <>
                    <button type="button" className={SECONDARY_BUTTON} onClick={onClose} disabled={pending}>{KB.closeWithoutSaving}</button>
                    <button type="button" className={SECONDARY_BUTTON} onClick={save} disabled={busy || !dirty}>
                        {pending ? KB.saving : KB.saveArticle}
                    </button>
                </>
            )}
        >
            <div className="flex flex-col gap-4">
                {starterCopy && <HealthNotice tone="blue" role="status"><p>{KB.starterCopyNote}</p></HealthNotice>}
                {load === 'loading' && <p role="status" className={MUTED}>{KB.articleLoading}</p>}
                {load === 'failed' && (
                    <HealthNotice tone="red" role="alert">
                        <p>{KB.articleLoadFailed}</p>
                        <div><button type="button" className={TEXT_BUTTON} onClick={() => setAttempt(n => n + 1)}>{KB.tryAgain}</button></div>
                    </HealthNotice>
                )}
                <div className="flex flex-col gap-1">
                    <label htmlFor={ids.title} className="text-sm font-semibold text-gray-900 dark:text-white">{KB.fieldTitle}</label>
                    <input
                        id={ids.title} value={title} maxLength={TITLE_MAX} disabled={busy} className={`${FIELD} w-full`}
                        aria-required="true" aria-invalid={!!errors.title} autoFocus={!editing}
                        onChange={e => { setTitle(e.target.value); setErrors(p => ({ ...p, title: undefined })); }}
                    />
                    {errors.title && <p role="alert" className={ERROR_LINE}>{errors.title}</p>}
                </div>
                <div className="flex flex-col gap-1">
                    <label htmlFor={ids.content} className="text-sm font-semibold text-gray-900 dark:text-white">{KB.fieldContent}</label>
                    <textarea
                        id={ids.content} value={content} disabled={busy} aria-required="true" aria-invalid={!!contentError}
                        aria-describedby={ids.count} className={`${FIELD} min-h-72 w-full overflow-y-auto py-2`}
                        onChange={e => { setContent(e.target.value); setErrors(p => ({ ...p, content: undefined })); }}
                    />
                    <p id={ids.count} className={`${MUTED} text-right ${over ? 'text-red-700 dark:text-red-300' : ''}`}>
                        {fill(KB.contentCounter, { n: content.length, max })}
                    </p>
                    {contentError && <p role="alert" className={ERROR_LINE}>{contentError}</p>}
                </div>
                <div className="flex flex-col gap-1">
                    <label htmlFor={ids.tags} className="text-sm font-semibold text-gray-900 dark:text-white">{KB.fieldTags}</label>
                    <input id={ids.tags} value={tags} disabled={busy} className={`${FIELD} w-full`} onChange={e => setTags(e.target.value)} />
                </div>
                <div className="flex flex-col gap-1">
                    <label className="flex min-h-10 items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white">
                        <input
                            type="checkbox" checked={helpdesk} disabled={busy} aria-describedby={ids.help}
                            onChange={e => setHelpdesk(e.target.checked)}
                        />
                        <span className="break-words">{KB.helpdeskCheckbox}</span>
                    </label>
                    <p id={ids.help} className={MUTED}>{KB.helpdeskHelper}</p>
                </div>
                {saveError && <HealthNotice tone="red" role="alert"><p>{saveError}</p></HealthNotice>}
            </div>
        </Modal>
    );
};
