import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { fetchGoLive } from '../../services/autonomousOpsGoLive';
import type { GoLiveOverview } from '../../services/autonomousOpsGoLive';
import { HEALTH_SKELETON, HealthNotice } from '../AutonomousOpsHealthChips';
import { ChevronRightIcon, ClipboardCheckIcon } from '../icons';
import { GoLiveChecklist } from './GoLiveChecklist';
import { GoLiveOrganizations } from './GoLiveOrganizations';
import {
    CHECK_TOTAL, GOLIVE_INTRO, GOLIVE_LOAD_ERROR, GOLIVE_LOAD_FAILED_SUMMARY, GOLIVE_TITLE, TRY_AGAIN, goLiveSummary,
} from './goLiveCopy';

/** A payload the card can draw: five checks in a list. Anything else is a failed load, never a half-drawn card. */
const isOverview = (v: unknown): v is GoLiveOverview => {
    const o = v as Partial<GoLiveOverview> | null;
    return !!o && Array.isArray(o.checks) && Array.isArray(o.organizations);
};

/**
 * The Going live card (86-UI-SPEC section 6, D-14): a collapsed row whose summary says how many of the five live checks are
 * recorded, and an expanded body with the intro and the checklist. Loaded on mount; refetched on expand and after every write.
 * No polling. Platform scope and the platform owner only; the screen decides that. The server enforces every gate; the card
 * only shows what it says. Everything from the server renders as React text.
 */
export const GoLiveCard: React.FC = () => {
    const uid = useId();
    const bodyId = `${uid}-body`;
    const [expanded, setExpanded] = useState(false);
    const [data, setData] = useState<GoLiveOverview | null>(null);
    const [failed, setFailed] = useState(false);
    const [loading, setLoading] = useState(true);
    const latest = useRef(0);

    const load = useCallback(async () => {
        const mine = ++latest.current;
        setLoading(true);
        try {
            const next = await fetchGoLive();
            if (mine !== latest.current) return;
            if (!isOverview(next)) throw new Error('unreadable go-live answer');
            setData(next);
            setFailed(false);
        } catch {
            if (mine !== latest.current) return;
            // A refetch that fails keeps what is already on screen; only a first load shows the error.
            setFailed(true);
        } finally {
            if (mine === latest.current) setLoading(false);
        }
    }, []);

    useEffect(() => { void load(); }, [load]);

    const toggle = () => {
        if (!expanded) void load();
        setExpanded(v => !v);
    };

    const outOfShadow = data ? data.organizations.filter(o => !o.shadow).length : 0;
    const recorded = data ? data.checks.filter(c => c.recorded).length : 0;
    const firstLoad = loading && !data;
    const showError = failed && !data;

    return (
        <section className="card p-6" aria-labelledby={`${uid}-title`}>
            <div className="min-w-0">
                <h2 id={`${uid}-title`} className="text-lg font-semibold leading-tight text-gray-900 dark:text-white">
                    <button type="button" aria-expanded={expanded} aria-controls={bodyId} onClick={toggle} className="inline-flex items-center gap-2 text-left">
                        <ClipboardCheckIcon size={20} aria-hidden="true" />
                        <span>{GOLIVE_TITLE}</span>
                        <ChevronRightIcon size={16} aria-hidden="true" className={expanded ? 'rotate-90' : ''} />
                    </button>
                </h2>
                {firstLoad && !showError && <div className={`mt-2 h-4 w-72 ${HEALTH_SKELETON}`} />}
                {data && <p className="mt-2 break-words text-sm text-gray-600 dark:text-gray-400">{goLiveSummary(recorded, outOfShadow)}</p>}
                {showError && <p className="mt-2 break-words text-sm text-gray-600 dark:text-gray-400">{GOLIVE_LOAD_FAILED_SUMMARY}</p>}
            </div>

            {expanded && (
                <div id={bodyId} aria-busy={firstLoad} className="mt-6 flex flex-col gap-6 border-t border-gray-200 pt-6 dark:border-white/10">
                    <p className="break-words text-sm text-gray-600 dark:text-gray-400">{GOLIVE_INTRO}</p>

                    {showError && (
                        <HealthNotice tone="red" role="alert">
                            <p>{GOLIVE_LOAD_ERROR}</p>
                            <p>
                                <button type="button" onClick={() => void load()} className="text-sm font-semibold underline underline-offset-2">{TRY_AGAIN}</button>
                            </p>
                        </HealthNotice>
                    )}

                    {firstLoad && !showError && (
                        <>
                            <div className="flex flex-col gap-4">
                                {Array.from({ length: CHECK_TOTAL }, (_, i) => <div key={i} className={`h-24 ${HEALTH_SKELETON}`} />)}
                            </div>
                            <div className={`h-40 ${HEALTH_SKELETON}`} />
                        </>
                    )}

                    {data && <GoLiveChecklist checks={data.checks} onRecorded={load} />}
                    {data && <GoLiveOrganizations organizations={data.organizations} masterShadow={!!data.masterShadow} onChanged={load} />}
                </div>
            )}
        </section>
    );
};

export default GoLiveCard;
