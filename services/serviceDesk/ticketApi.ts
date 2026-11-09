import { API_BASE, authFetch } from '../apiService';
import { failure } from '../autonomousOpsApi';
import type { ArticleView, Citation, RequesterItem, RequesterView, TicketDeskView } from './types';

/**
 * The ticket-screen routes of the first-line service desk (85-14). Who may do what is decided by the server per
 * ticket: the staff draft routes need view:dashboard and refuse the person who raised the ticket (403), the
 * confirm and help routes need view:dashboard and accept only that person, and every ticket is read inside the
 * caller's own tenant (any other ticket answers 404). Each call throws an `AutonomousOpsApiError` (`status`,
 * `detail`) for a non-OK answer; the screens word the failure, the client never works out who may act.
 */

/** What the server stores as a comment kind, as the requester view sends it. */
interface RawRequesterItem {
    id: string;
    kind: string | null;
    at: string;
    author: string | null;
    text: string;
    citations?: Citation[] | null;
}

type RawRequesterView = Omit<RequesterView, 'items'> & { items?: RawRequesterItem[] | null };
type RawTicketDeskView = Omit<TicketDeskView, 'requester'> & { requester: RawRequesterView | null };

/**
 * The one place the server's stored comment kinds become the client's `RequesterItem.kind` (85-02 types):
 * `ai_answer` is an answer, `requester_reply` is the requester's own note, `withdrawn_notice` a withdrawn answer,
 * `handoff_notice` a notice, and no kind at all (null) is a plain reply from IT. A kind this build does not know
 * reads as a notice, never as a reply from a person.
 */
export function mapRequesterKind(kind: string | null | undefined): RequesterItem['kind'] {
    switch (kind) {
        case 'ai_answer': return 'answer';
        case 'requester_reply': return 'you';
        case 'withdrawn_notice': return 'withdrawn';
        case 'handoff_notice': return 'notice';
        case null:
        case undefined: return 'reply';
        default: return 'notice';
    }
}

function mapRequester(raw: RawRequesterView | null | undefined): RequesterView | null {
    if (!raw) return null;
    const items = (raw.items ?? []).map((item): RequesterItem => ({
        id: item.id,
        kind: mapRequesterKind(item.kind),
        at: item.at,
        author: item.author ?? null,
        text: typeof item.text === 'string' ? item.text : '',
        citations: Array.isArray(item.citations) ? item.citations : [],
    }));
    return { ...raw, items };
}

const deskUrl = (ticketId: string, rest = '') => `${API_BASE}/tickets/${encodeURIComponent(ticketId)}/service-desk${rest}`;

async function send<T>(url: string, body?: unknown): Promise<T> {
    const res = await authFetch(url, { method: 'POST', body: JSON.stringify(body ?? {}) });
    if (!res.ok) throw await failure(res);
    return res.json();
}

/** The answer of a draft route: what happened to the draft. */
export interface DraftActionResult {
    status: 'sent' | 'discarded';
    commentId: string;
    edited?: boolean;
}

/** GET /api/tickets/{id}/service-desk (view:dashboard): the desk view of one ticket. The reporter gets `requester` and never a draft; everyone else in the tenant gets `draft` and no `requester`. The requester items arrive with the client kinds (see mapRequesterKind). */
export async function fetchTicketDesk(ticketId: string): Promise<TicketDeskView> {
    const res = await authFetch(deskUrl(ticketId));
    if (!res.ok) throw await failure(res);
    const raw = (await res.json()) as RawTicketDeskView;
    return { ...raw, requester: mapRequester(raw.requester) };
}

/** POST /api/tickets/{id}/service-desk/drafts/{commentId}/send (view:dashboard, not the reporter): shows the draft to the requester as it is and moves the ticket to Waiting on customer. 409 {detail} when it was already handled, the ticket is closed or a person already replied. */
export function sendDraft(ticketId: string, commentId: string): Promise<DraftActionResult> {
    return send(deskUrl(ticketId, `/drafts/${encodeURIComponent(commentId)}/send`));
}

/** POST /api/tickets/{id}/service-desk/drafts/{commentId}/edit (view:dashboard, not the reporter): sends the edited text under the same label and citations. 422 {detail} when it is empty, over the limit or unchanged; 409 as for send. */
export function editAndSendDraft(ticketId: string, commentId: string, text: string): Promise<DraftActionResult> {
    return send(deskUrl(ticketId, `/drafts/${encodeURIComponent(commentId)}/edit`), { text });
}

/** POST /api/tickets/{id}/service-desk/drafts/{commentId}/discard (view:dashboard, not the reporter): the requester never sees the draft and there is no second attempt. 409 {detail} when it was already handled. */
export function discardDraft(ticketId: string, commentId: string): Promise<DraftActionResult> {
    return send(deskUrl(ticketId, `/drafts/${encodeURIComponent(commentId)}/discard`));
}

/** POST /api/tickets/{id}/service-desk/confirm (view:dashboard, only the person who raised the ticket): This fixed it. Resolves the ticket. 409 {detail} when no answer is waiting on them. */
export function confirmFixed(ticketId: string): Promise<{ status: 'confirmed' }> {
    return send(deskUrl(ticketId, '/confirm'));
}

/** POST /api/tickets/{id}/service-desk/help (view:dashboard, only the person who raised the ticket): I still need help. The optional note is up to 1,000 characters (422 {detail} over it); the ticket goes to a person. */
export function stillNeedHelp(ticketId: string, text?: string): Promise<{ status: 'helped' }> {
    const note = text?.trim();
    return send(deskUrl(ticketId, '/help'), note ? { text: note } : {});
}

/** GET /api/tickets/{id}/service-desk/articles/{articleId} (view:dashboard): one cited article, read-only. Only an article cited on this ticket opens (404 {detail} for any other); a deleted one answers `available: false` with its cited title. */
export async function fetchCitedArticle(ticketId: string, articleId: string): Promise<ArticleView> {
    const res = await authFetch(deskUrl(ticketId, `/articles/${encodeURIComponent(articleId)}`));
    if (!res.ok) throw await failure(res);
    return res.json();
}

/** Who sees a comment: `staff` (the default) or the `requester` (D-11). */
export type CommentVisibility = 'staff' | 'requester';

/** POST /api/tickets/{id}/comments (the ticket's reply permission): adds a comment and answers the updated ticket. `requester` is refused 400 {detail} on a ticket raised by an automated source or one the requester cannot read. */
export async function postTicketComment(ticketId: string, text: string, visibility: CommentVisibility): Promise<any> {
    const res = await authFetch(`${API_BASE}/tickets/${encodeURIComponent(ticketId)}/comments`, {
        method: 'POST', body: JSON.stringify({ text, visibility }),
    });
    if (!res.ok) throw await failure(res);
    return res.json();
}
