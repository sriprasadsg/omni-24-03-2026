import React, { useEffect, useId, useRef, useState } from 'react';
import { ChevronRightIcon, FileTextIcon } from '../icons';
import { fetchCitedArticle } from '../../services/serviceDesk/ticketApi';
import type { Citation } from '../../services/serviceDesk/types';
import { BODY_TEXT, ERROR_LINE, MUTED, TEXT_BUTTON } from './deskUi';
import { CITED } from './serviceDeskCopy';

type Loaded =
    | { state: 'loading' }
    | { state: 'error' }
    | { state: 'gone' }
    | { state: 'ready'; content: string };

interface Props {
    ticketId: string;
    citations: Citation[];
}

/**
 * The read-only list of the articles an answer cites (UI-SPEC 3 item 4 and 4 item 4; D-14), shared by the staff draft
 * panel and the requester's answer panel. Each citation is a disclosure button; opening it reads the article once
 * from the ticket's own route (only an article cited on this ticket opens). A deleted article keeps its title and says
 * so. Everything the server sends is rendered as text.
 */
export const CitedArticles: React.FC<Props> = ({ ticketId, citations }) => {
    const [open, setOpen] = useState<Record<string, boolean>>({});
    const [loaded, setLoaded] = useState<Record<string, Loaded>>({});
    const live = useRef(true);
    const asked = useRef<Set<string>>(new Set());
    const baseId = useId();

    useEffect(() => {
        live.current = true;
        return () => { live.current = false; };
    }, []);

    const load = (articleId: string) => {
        asked.current.add(articleId);
        setLoaded(prev => ({ ...prev, [articleId]: { state: 'loading' } }));
        fetchCitedArticle(ticketId, articleId).then(
            article => {
                if (!live.current) return;
                setLoaded(prev => ({
                    ...prev,
                    [articleId]: article.available ? { state: 'ready', content: article.content ?? '' } : { state: 'gone' },
                }));
            },
            () => {
                if (!live.current) return;
                asked.current.delete(articleId);
                setLoaded(prev => ({ ...prev, [articleId]: { state: 'error' } }));
            },
        );
    };

    const toggle = (citation: Citation) => {
        const id = citation.articleId;
        const next = !open[id];
        setOpen(prev => ({ ...prev, [id]: next }));
        if (!next || asked.current.has(id)) return;
        if (citation.available === false) {
            asked.current.add(id);
            setLoaded(prev => ({ ...prev, [id]: { state: 'gone' } }));
            return;
        }
        load(id);
    };

    if (!citations.length) return null;
    return (
        <ul className="flex flex-col gap-2">
            {citations.map((citation, index) => {
                const id = citation.articleId;
                const regionId = `${baseId}-article-${index}`;
                const expanded = open[id] === true;
                const result = loaded[id];
                return (
                    <li key={`${id}-${index}`} className="min-w-0">
                        <button
                            type="button"
                            className="flex min-h-10 w-full items-center gap-2 rounded-lg px-2 text-left hover:bg-gray-50 dark:hover:bg-white/5"
                            aria-expanded={expanded}
                            aria-controls={regionId}
                            onClick={() => toggle(citation)}
                        >
                            <FileTextIcon size={16} aria-hidden="true" className="shrink-0" />
                            <span className="min-w-0 flex-1 break-words text-sm font-semibold text-gray-900 dark:text-white">{citation.title}</span>
                            <ChevronRightIcon size={16} aria-hidden="true" className={`shrink-0 transition-transform ${expanded ? 'rotate-90' : ''}`} />
                        </button>
                        {expanded && (
                            <div id={regionId} className="mt-2 max-h-64 overflow-y-auto rounded-lg border border-gray-200 p-4 dark:border-white/10">
                                {(!result || result.state === 'loading') && <p role="status" className={MUTED}>{CITED.loading}</p>}
                                {result?.state === 'error' && (
                                    <div className="flex flex-wrap items-center gap-2">
                                        <p role="alert" className={ERROR_LINE}>{CITED.error}</p>
                                        <button type="button" className={TEXT_BUTTON} onClick={() => load(id)}>{CITED.tryAgain}</button>
                                    </div>
                                )}
                                {result?.state === 'gone' && <p className={BODY_TEXT}>{CITED.gone}</p>}
                                {result?.state === 'ready' && (
                                    <div className="flex flex-col gap-2">
                                        <p className={BODY_TEXT}>{result.content}</p>
                                        <p className={MUTED}>{CITED.readOnly}</p>
                                    </div>
                                )}
                            </div>
                        )}
                    </li>
                );
            })}
        </ul>
    );
};
