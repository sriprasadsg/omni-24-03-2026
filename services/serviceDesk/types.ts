/**
 * Request and response types for every route of the first-line service desk (Phase 85).
 *
 * The server decides who may do what and sends flags (`canManage`, `canRestore`, `canActOnDraft`,
 * `canReplyToRequester`, `isRequester`, `canConfirm`, `canUndo`, `canManageArticles`, `canSeeGaps`); the
 * client never derives them. Every string a response carries is rendered as text, never as HTML.
 * Timestamps are ISO 8601 strings.
 */

/** The three modes, exactly (D-03). */
export type DeskMode = 'off' | 'drafts' | 'post';

/** Why a qualifying answer would not be posted right now (the readiness list, UI-SPEC section 2d). */
export interface PostingBlocker {
    code: 'level' | 'shadow' | 'stop' | 'hourly_limit' | 'desk_breaker';
    /** Present for `level`: the tenant's current Autonomous Ops level, for the text. */
    level?: string;
}

export interface DeskSettingsView {
    /** What the tenant saved. */
    mode: DeskMode;
    /** What actually applies: Off when the Tickets or Knowledge Base screen is off. */
    effectiveMode: DeskMode;
    /** False when the stored settings could not be read; answers are drafts until they load. */
    readable: boolean;
    /** Whether the Tickets and Knowledge Base screens are both switched on for this tenant. */
    screensOn: boolean;
    /** The tenant's extra hand-off words. */
    words: string[];
    maxWords: number;
    /** Set when the desk breaker tripped (3 withdrawals within 24 hours). */
    breaker: { trippedAt: string; count: number } | null;
    posting: { posting: boolean; blockers: PostingBlocker[] };
    model: { state: 'online' | 'offline' | 'not_checked'; tag: string | null };
    /** Typical answer time (DESK-05): the median of the last `samples` answers, in seconds. */
    timing: { medianSeconds: number | null; samples: number; measured: boolean };
    canManage: boolean;
    canRestore: boolean;
}

/** Changes sent with Save. Either key may be left out. */
export interface DeskSettingsChanges {
    mode?: DeskMode;
    words?: string[];
}

/** One article a desk answer cites. `available` is false when the article was deleted since. */
export interface Citation {
    articleId: string;
    title: string;
    available?: boolean;
}

/** One item of the requester view: an AI answer, a reply from IT, or the requester's own note. */
export interface RequesterItem {
    id: string;
    kind: 'answer' | 'reply' | 'you' | 'withdrawn' | 'notice';
    at: string;
    author: string | null;
    text: string;
    citations: Citation[];
}

export interface RequesterView {
    items: RequesterItem[];
    canConfirm: boolean;
    /** When a person from IT picks the ticket up if the requester stays silent (from postedAt). */
    returnAt: string | null;
    notice: 'confirmed' | 'helped' | 'handed_off' | 'withdrawn' | null;
    confirmedAt: string | null;
}

/** The staff draft panel (UI-SPEC section 3). Present only while a draft is waiting. */
export interface DraftView {
    commentId: string;
    actionId: string;
    answer: string;
    citations: Citation[];
    createdAt: string;
    articleCount: number;
    draftReason: string | null;
    draftReasonText: string | null;
    maxAnswerLength: number;
    canActOnDraft: boolean;
    /** Why sending is blocked (ticket resolved or closed, a person already replied), or null. */
    blockedReason: string | null;
    blockedText: string | null;
    reporter: string;
}

/** GET of the desk view of one ticket. */
export interface TicketDeskView {
    ticketId: string;
    ticketNumber: string;
    status: string;
    isRequester: boolean;
    requester: RequesterView | null;
    draft: DraftView | null;
    canReplyToRequester: boolean;
    draftWaiting: boolean;
}

/** One cited article opened read-only. */
export interface ArticleView {
    articleId: string;
    title: string;
    content: string;
    available: boolean;
}

export interface KnowledgeGapGroup {
    id: string;
    question: string;
    count: number;
    lastAskedAt: string;
    tickets: Array<{ id: string; number: string }>;
    status: 'open' | 'dismissed';
}

export interface GapsView {
    groups: KnowledgeGapGroup[];
    otherLanguageCount: number;
    dismissedCount: number;
    deskOff: boolean;
}

/** How many of the four starter articles a tenant does not have yet. */
export interface StarterStatus {
    total: number;
    missing: number;
}

export interface StarterResult {
    added: number;
    existing: number;
    addedKeys: string[];
}

/** A change to a Help desk article. Every key may be left out. */
export interface HelpdeskDocPatch {
    title?: string;
    content?: string;
    tags?: string[];
    helpdesk?: boolean;
}

/** Flags the Knowledge Base screen reads from the server. */
export interface KbDocFlags {
    canManageArticles: boolean;
    canSeeGaps: boolean;
    helpdeskCount: number;
    starterMissing: number;
    deskOff: boolean;
}

/** The two ticket fields an Activity row carries when it belongs to the desk. */
export interface ActivityDeskFields {
    ticketId: string | null;
    ticketNumber: string | null;
}

/** The response of Undo on a posted answer. */
export interface UndoResult {
    status: string;
    breakerTripped: boolean;
    deskBreakerTripped: boolean;
}
