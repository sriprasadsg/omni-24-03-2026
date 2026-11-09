/**
 * Phase 85 / DESK-01 (85-26, CR-401 UI half, D-11): which comments of a ticket the person who raised it may read.
 *
 * This is a TypeScript copy of `projection.requester_may_read` in backend/service_desk/projection.py. The two are
 * pinned to one case table, shared/service-desk-requester-comments.json, which both test suites read, so they cannot
 * drift. With the server projection of 85-25 the reporter's browser no longer receives the hidden comments; this
 * filter is defence in depth for an older or misbehaving server and for the moments before the desk view answers.
 */

/** The parts of a stored comment the rule reads; the dashboard's own Comment type fits it. */
export interface RequesterComment {
    author?: string | null;
    visibility?: string | null;
    kind?: string | null;
    ai?: { state?: string } | null;
}

/** The parts of a stored ticket the rule reads. */
export interface RequesterTicket<C extends RequesterComment = RequesterComment> {
    reporter?: string | null;
    comments?: C[] | null;
}

const clean = (value: unknown): string => (typeof value === 'string' ? value.trim().toLowerCase() : '');

/** True when both names are the same person, ignoring case and surrounding spaces; an empty first name is nobody. */
export function sameUser(a: unknown, b: unknown): boolean {
    const first = clean(a);
    return first !== '' && first === clean(b);
}

/**
 * True when the reporter may read `comment` of their own ticket: a comment marked for the requester that is not a
 * withdrawn answer, or any comment the reporter wrote (the portal stores it staff-only by default). Never an AI draft.
 */
export function requesterMayRead(ticket: { reporter?: string | null }, comment: unknown): boolean {
    if (typeof comment !== 'object' || comment === null) return false;
    const c = comment as RequesterComment;
    if (c.kind === 'ai_draft') return false;
    const withdrawn = c.kind === 'ai_answer' && c.ai?.state === 'withdrawn';
    return (c.visibility === 'requester' && !withdrawn) || sameUser(ticket.reporter, c.author);
}

/**
 * Whether the signed-in user is treated as the ticket's reporter. Decided from the ticket and the signed-in email, not
 * only from the desk view, so the answer is already right on the first paint and after a failed desk read. An unknown
 * viewer (no email) with no desk view is treated as the reporter: the list fails closed.
 */
export function viewerIsReporter(
    ticket: { reporter?: string | null },
    viewerEmail: string | null | undefined,
    deskView: { isRequester?: boolean } | null | undefined,
): boolean {
    if (deskView?.isRequester === true) return true;
    if (sameUser(ticket.reporter, viewerEmail)) return true;
    return !deskView && clean(viewerEmail) === '';
}

/** The ticket's comments as the signed-in user may read them: all of them for staff, the readable ones for the reporter. */
export function visibleComments<C extends RequesterComment>(
    ticket: RequesterTicket<C>,
    viewerEmail: string | null | undefined,
    deskView: { isRequester?: boolean } | null | undefined,
): C[] {
    const all = Array.isArray(ticket.comments) ? ticket.comments : [];
    return viewerIsReporter(ticket, viewerEmail, deskView) ? all.filter(c => requesterMayRead(ticket, c)) : all;
}
