import React, { useCallback, useEffect, useState } from 'react';
import { EmptyStateCard } from '../AutonomousOpsActivityList';
import { InfoIcon, PencilIcon, XIcon } from '../icons';
import { showToast } from '../../utils/toast';
import { dismissGap, fetchGaps, restoreGap } from '../../services/serviceDesk/knowledgeApi';
import type { GapsView, KnowledgeGapGroup } from '../../services/serviceDesk/types';
import { DeskChip, HealthNotice, MUTED, SECONDARY_BUTTON, TEXT_BUTTON, failureLine, relativeWords } from './deskUi';
import { ACTIVITY, GAPS, TOASTS, fill } from './serviceDeskCopy';

const PAGE = 10;
const FIRST_TICKETS = 3;

interface Props {
    /** Told how many groups are open after every read and every dismiss or restore, so the tab label stays right. */
    onOpenCount: (n: number) => void;
    /** Write article: the screen opens its article dialog for this group. */
    onWrite: (group: KnowledgeGapGroup) => void;
    /** Changes when something outside the tab closed a gap (an article was saved), so the tab reads again. */
    refreshKey?: number;
    /** Opens a ticket on the Tickets screen; without it the ticket numbers are plain text. */
    onOpenTicket?: (ticketId: string, number: string) => void;
}

const openCount = (view: GapsView) => view.groups.filter(g => g.status === 'open').length;

/** "Last asked 2 hours ago", or just the count when the moment is unreadable. */
function metaLine(group: KnowledgeGapGroup): string {
    const relative = relativeWords(group.lastAskedAt);
    if (!relative) return group.count === 1 ? GAPS.countOne : fill(GAPS.count, { n: group.count });
    return group.count === 1 ? fill(GAPS.metaOne, { relative }) : fill(GAPS.meta, { n: group.count, relative });
}

const TicketRef: React.FC<{ id: string; number: string; onOpen?: Props['onOpenTicket'] }> = ({ id, number, onOpen }) => (
    onOpen ? (
        <button type="button" className={`${TEXT_BUTTON} font-mono text-xs font-normal`} onClick={() => onOpen(id, number)}
            aria-label={fill(ACTIVITY.openTicket, { number })}>{number}</button>
    ) : (
        <span className="font-mono text-xs text-gray-700 dark:text-gray-200">{number}</span>
    )
);

/**
 * The Knowledge gaps tab (UI-SPEC section 6, D-26, D-27): questions requesters asked that no Help desk article answered,
 * grouped by topic by the server. Authors write the article that closes a gap or set the group aside, and can bring a
 * dismissed group back. It is shown only when the server says the caller may see gaps (it needs ticket and Knowledge Base
 * access together), reads once when it opens and again only on Try again or when an article closes a gap; it never polls.
 */
export const KnowledgeGapsTab: React.FC<Props> = ({ onOpenCount, onWrite, refreshKey = 0, onOpenTicket }) => {
    const [view, setView] = useState<GapsView | null>(null);
    const [failed, setFailed] = useState(false);
    const [attempt, setAttempt] = useState(0);
    const [showDismissed, setShowDismissed] = useState(false);
    const [limit, setLimit] = useState(PAGE);
    const [expanded, setExpanded] = useState<Set<string>>(new Set());
    const [busy, setBusy] = useState<{ id: string; action: 'dismiss' | 'restore' } | null>(null);
    const [problem, setProblem] = useState<{ id: string; text: string } | null>(null);

    useEffect(() => {
        let cancelled = false;
        setFailed(false);
        fetchGaps(true).then(next => { if (!cancelled) setView(next); }).catch(() => { if (!cancelled) setFailed(true); });
        return () => { cancelled = true; };
    }, [attempt, refreshKey]);

    // The screen's tab label follows what is open here, after every read, dismiss and restore.
    useEffect(() => { if (view) onOpenCount(openCount(view)); }, [view, onOpenCount]);

    const change = useCallback((id: string, status: 'open' | 'dismissed') => {
        setView(prev => {
            if (!prev) return prev;
            const groups = prev.groups.map(g => (g.id === id ? { ...g, status } : g));
            return { ...prev, groups, dismissedCount: groups.filter(g => g.status === 'dismissed').length };
        });
    }, []);

    async function act(group: KnowledgeGapGroup, action: 'dismiss' | 'restore') {
        if (busy) return;
        setBusy({ id: group.id, action });
        setProblem(null);
        try {
            if (action === 'dismiss') {
                await dismissGap(group.id);
                showToast(TOASTS.gapDismissed, 'success');
                change(group.id, 'dismissed');
            } else {
                await restoreGap(group.id);
                change(group.id, 'open');
            }
        } catch (e) {
            setProblem({ id: group.id, text: failureLine(e, GAPS.actionFailed, GAPS.actionFailedFallback) });
        } finally {
            setBusy(null);
        }
    }

    const dismissed = view?.dismissedCount ?? 0;
    const dismissedShown = showDismissed && dismissed > 0;
    const groups = (view?.groups ?? []).filter(g => dismissedShown || g.status === 'open');
    const page = groups.slice(0, limit);

    return (
        <section className="flex flex-col gap-4" aria-labelledby="kb-gaps-heading">
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0 max-w-3xl">
                    <h2 id="kb-gaps-heading" className="text-lg font-semibold text-gray-900 dark:text-white">{GAPS.heading}</h2>
                    <p className="mt-1 break-words text-sm text-gray-600 dark:text-gray-400">{GAPS.intro}</p>
                </div>
                {dismissed > 0 && (
                    <button type="button" className={TEXT_BUTTON} aria-pressed={dismissedShown} onClick={() => setShowDismissed(v => !v)}>
                        {dismissedShown ? GAPS.hideDismissed : fill(GAPS.showDismissed, { d: dismissed })}
                    </button>
                )}
            </div>

            {failed && (
                <HealthNotice tone="red" role="alert">
                    <p>{GAPS.loadFailed}</p>
                    <div><button type="button" className={TEXT_BUTTON} onClick={() => setAttempt(n => n + 1)}>{GAPS.tryAgain}</button></div>
                </HealthNotice>
            )}

            {!failed && !view && (
                <div data-testid="gaps-loading" aria-busy="true" className="flex flex-col gap-4">
                    {[0, 1, 2].map(i => <div key={i} className="card h-24 animate-pulse" />)}
                </div>
            )}

            {view && !failed && (
                <>
                    {groups.length === 0 ? (
                        <div className="card">
                            {view.deskOff ? (
                                <EmptyStateCard icon={InfoIcon} heading={GAPS.emptyOffHeading}>
                                    <p className="max-w-prose break-words text-sm text-gray-600 dark:text-gray-400">{GAPS.emptyOffBody}</p>
                                </EmptyStateCard>
                            ) : (
                                <EmptyStateCard icon={InfoIcon} heading={GAPS.emptyHeading}>
                                    <p className="max-w-prose break-words text-sm text-gray-600 dark:text-gray-400">{GAPS.emptyBody}</p>
                                </EmptyStateCard>
                            )}
                        </div>
                    ) : (
                        <ul aria-label={GAPS.listLabel} className="flex flex-col gap-4">
                            {page.map(group => {
                                const all = expanded.has(group.id);
                                const links = all ? group.tickets : group.tickets.slice(0, FIRST_TICKETS);
                                const working = busy?.id === group.id ? busy.action : null;
                                return (
                                    <li key={group.id} className="card flex flex-col gap-2 p-4">
                                        <div className="flex flex-wrap items-center gap-2">
                                            <p className="break-words text-sm font-semibold text-gray-900 dark:text-white">{group.question}</p>
                                            {group.status === 'dismissed' && <DeskChip tone="outline" icon={XIcon}>{GAPS.chipDismissed}</DeskChip>}
                                        </div>
                                        <p className={MUTED}>{metaLine(group)}</p>
                                        {links.length > 0 && (
                                            <div className="flex flex-wrap items-center gap-2">
                                                {links.map(t => <TicketRef key={t.id} id={t.id} number={t.number} onOpen={onOpenTicket} />)}
                                                {group.tickets.length > FIRST_TICKETS && (
                                                    <button type="button" className={TEXT_BUTTON} aria-expanded={all}
                                                        onClick={() => setExpanded(prev => {
                                                            const next = new Set(prev);
                                                            if (all) next.delete(group.id); else next.add(group.id);
                                                            return next;
                                                        })}>
                                                        {fill(GAPS.showAllTickets, { n: group.tickets.length })}
                                                    </button>
                                                )}
                                            </div>
                                        )}
                                        <div className="flex flex-wrap items-center gap-2">
                                            {group.status === 'dismissed' ? (
                                                <button type="button" className={SECONDARY_BUTTON} disabled={!!busy}
                                                    aria-label={working ? undefined : `${GAPS.restore}: ${group.question}`} onClick={() => act(group, 'restore')}>
                                                    {working === 'restore' ? GAPS.restoring : GAPS.restore}
                                                </button>
                                            ) : (
                                                <>
                                                    <button type="button" className={SECONDARY_BUTTON} disabled={!!busy}
                                                        aria-label={`${GAPS.writeArticle}: ${group.question}`} onClick={() => onWrite(group)}>
                                                        <PencilIcon size={16} aria-hidden="true" />
                                                        {GAPS.writeArticle}
                                                    </button>
                                                    <button type="button" className={SECONDARY_BUTTON} disabled={!!busy}
                                                        aria-label={working ? undefined : `${GAPS.dismiss}: ${group.question}`} onClick={() => act(group, 'dismiss')}>
                                                        <XIcon size={16} aria-hidden="true" />
                                                        {working === 'dismiss' ? GAPS.dismissing : GAPS.dismiss}
                                                    </button>
                                                </>
                                            )}
                                        </div>
                                        {problem?.id === group.id && <p role="alert" className="break-words text-sm text-red-700 dark:text-red-300">{problem.text}</p>}
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                    {groups.length > page.length && (
                        <div><button type="button" className={SECONDARY_BUTTON} onClick={() => setLimit(n => n + PAGE)}>{GAPS.showMore}</button></div>
                    )}
                    {view.otherLanguageCount > 0 && (
                        <div className="card flex items-start gap-2 p-4">
                            <InfoIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-gray-500 dark:text-gray-400" />
                            <p className={MUTED}>
                                {view.otherLanguageCount === 1 ? GAPS.otherLanguageOne : fill(GAPS.otherLanguage, { n: view.otherLanguageCount })}
                            </p>
                        </div>
                    )}
                    <p className={MUTED}>{GAPS.footnote}</p>
                </>
            )}
        </section>
    );
};
