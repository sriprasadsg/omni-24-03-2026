import { API_BASE, authFetch } from '../apiService';
import { failure } from '../autonomousOpsApi';
import type { GapsView, HelpdeskDocPatch, StarterResult, StarterStatus } from './types';

/**
 * The Knowledge Base routes of the first-line service desk (85-15, one added in 85-21). Every route sits behind the
 * Knowledge Base screen guard and works inside the caller's own organization; a shared (platform) article and another
 * organization's article answer 404, and the Platform organization itself is refused (403 `platform_tenant`). Each call
 * throws an `AutonomousOpsApiError` (`status`, `detail`) for a non-OK answer; the screens word the failure and the
 * client never works out who may act: the screen shows what the server's flags (`canManageArticles`, `canSeeGaps`) allow.
 */

/** The longest article the server accepts for the desk, used until the server states its own limit. */
export const DEFAULT_ARTICLE_MAX = 20000;

/** One of the organization's own articles, with its text. `max` is the server's character limit. */
export interface ArticleDetail {
    id: string;
    title: string;
    content: string;
    tags: string[];
    helpdesk: boolean;
    starterKey: string | null;
    max?: number;
}

/** The body of a new article. `gapGroupId` closes the knowledge gap the article answers. */
export interface NewArticle {
    title: string;
    content: string;
    tags: string[];
    helpdesk: boolean;
    gapGroupId?: string;
}

async function call<T>(url: string, init?: RequestInit): Promise<T> {
    const res = await authFetch(url, init);
    if (!res.ok) throw await failure(res);
    return res.json();
}

const post = (body?: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body ?? {}) });

/** GET /api/knowledge/docs/{id} (manage:ai_risks): one of the organization's own articles with its text, for the Edit article dialog. 404 {detail} for a shared or another organization's article. */
export function fetchArticle(docId: string): Promise<ArticleDetail> {
    return call(`${API_BASE}/knowledge/docs/${encodeURIComponent(docId)}`);
}

/** PATCH /api/knowledge/docs/{id} (manage:ai_risks): changes the keys given (title 1-200, text, tags, the Help desk mark). 422 {detail} for a refused value, 404 for a shared article, 403 {detail} when the Platform organization marks Help desk. */
export function patchArticle(docId: string, patch: HelpdeskDocPatch): Promise<unknown> {
    return call(`${API_BASE}/knowledge/docs/${encodeURIComponent(docId)}`, { method: 'PATCH', body: JSON.stringify(patch) });
}

/** POST /api/knowledge/helpdesk/articles (manage:ai_risks and view:dashboard): saves a new article; with `gapGroupId` the question group it answers is closed. 404 {detail} when the group is gone or was already written. */
export function createArticle(body: NewArticle): Promise<{ id: string; title: string; helpdesk: boolean; gapsWritten: number }> {
    return call(`${API_BASE}/knowledge/helpdesk/articles`, post(body));
}

/** GET /api/knowledge/helpdesk/starters (manage:ai_risks): how many of the four starter articles this organization does not have yet. */
export function fetchStarterStatus(): Promise<StarterStatus> {
    return call(`${API_BASE}/knowledge/helpdesk/starters`);
}

/** POST /api/knowledge/helpdesk/starters (manage:ai_risks): adds the missing starter articles as editable Help desk copies; pressing it again adds nothing twice (`existing` counts what was already there). */
export function addStarters(): Promise<StarterResult> {
    return call(`${API_BASE}/knowledge/helpdesk/starters`, post());
}

/** GET /api/knowledge/helpdesk/gaps[?dismissed=true] (manage:ai_risks and view:dashboard): the grouped questions no Help desk article answered; with `includeDismissed` the dismissed groups come too, each with its status. */
export function fetchGaps(includeDismissed = false): Promise<GapsView> {
    return call(`${API_BASE}/knowledge/helpdesk/gaps${includeDismissed ? '?dismissed=true' : ''}`);
}

/** POST /api/knowledge/helpdesk/gaps/{id}/dismiss (manage:ai_risks and view:dashboard): sets the group aside. Pressing it twice answers 200 with `changed` 0. */
export function dismissGap(groupId: string): Promise<{ status: string; changed: number }> {
    return call(`${API_BASE}/knowledge/helpdesk/gaps/${encodeURIComponent(groupId)}/dismiss`, post());
}

/** POST /api/knowledge/helpdesk/gaps/{id}/restore (manage:ai_risks and view:dashboard): brings a dismissed group back. Idempotent like dismiss. */
export function restoreGap(groupId: string): Promise<{ status: string; changed: number }> {
    return call(`${API_BASE}/knowledge/helpdesk/gaps/${encodeURIComponent(groupId)}/restore`, post());
}
