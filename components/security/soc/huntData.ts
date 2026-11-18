// Data helpers for SOC hunting (backend/soc_hunt.py, /api/security/soc/hunts): one structured query over SOC
// alerts, SIEM events or agent logs, saved hunts, and a hunt over SIEM events turned into a SIEM rule.
import { authFetch } from '../../../services/apiService';

export type HuntSource = 'alerts' | 'events' | 'logs';
export type HuntOp = 'eq' | 'ne' | 'in' | 'contains' | 'regex' | 'exists';
export type HuntRange = '1h' | '24h' | '7d' | '30d' | '90d';
export type FilterValue = string | number | boolean | (string | number)[];
export interface HuntFilter { field: string; op: HuntOp; value: FilterValue }
export interface HuntQuery { source: HuntSource; filters: HuntFilter[]; text: string; range: HuntRange; countBy: string | null }
/** The editor's copy: every value is text ('any of' comma separated, 'is present' yes/no). */
export interface DraftFilter { field: string; op: HuntOp; value: string }
export interface HuntDraft extends Omit<HuntQuery, 'filters'> { filters: DraftFilter[] }
export interface HuntField { name: string; label: string; values: (string | number)[]; ruleable: boolean }
export interface HuntSourceInfo { label: string; fields: HuntField[]; text: string }
export interface HuntCatalogue { sources: Record<HuntSource, HuntSourceInfo>; ranges: HuntRange[] }
export interface HuntRow { time?: string | null; text?: string; hostname?: string | null; agentId?: string | null; [field: string]: unknown }
export interface HuntGroup { value: string | number | null; count: number; label?: string | null }
export interface HuntResult { query: HuntQuery; total: number; rows: HuntRow[]; groups: HuntGroup[]; groupCount: number; since: string; until: string; tookMs: number }
export interface SavedHunt {
    id: string; name: string; description?: string | null; query: HuntQuery; createdBy?: string; updatedAt?: string;
    runCount?: number; lastRunAt?: string | null; lastCount?: number | null; ruleId?: string | null;
}
export interface HuntList { items: SavedHunt[]; canEdit: boolean; canMakeRules: boolean }
export type RuleSeverity = 'Critical' | 'High' | 'Medium' | 'Low';
export interface RuleDraft { name: string; severity: RuleSeverity; count: number; windowMinutes: number; alertNow: boolean }

export const SOURCES: HuntSource[] = ['events', 'alerts', 'logs'];
export const RANGES: HuntRange[] = ['1h', '24h', '7d', '30d', '90d'];
export const RANGE_LABEL: Record<HuntRange, string> = { '1h': 'hour', '24h': '24 hours', '7d': '7 days', '30d': '30 days', '90d': '90 days' };
export const OPS: HuntOp[] = ['eq', 'ne', 'in', 'contains', 'regex', 'exists'];
export const OP_LABEL: Record<HuntOp, string> = {
    eq: 'equals', ne: 'does not equal', in: 'is any of', contains: 'contains', regex: 'matches pattern', exists: 'is present',
};
export const EMPTY_DRAFT: HuntDraft = { source: 'events', filters: [], text: '', range: '24h', countBy: null };
export const RULE_SEVERITIES: RuleSeverity[] = ['Critical', 'High', 'Medium', 'Low'];

/** Columns of the result table per source; "endpoint" is the hostname, else the agent id. */
export const COLUMNS: Record<HuntSource, { key: string; label: string; mono?: boolean; wide?: boolean }[]> = {
    alerts: [{ key: 'severity', label: 'Severity' }, { key: 'type', label: 'Detection' }, { key: 'text', label: 'Title', wide: true },
        { key: 'endpoint', label: 'Endpoint' }, { key: 'status', label: 'Status' }],
    events: [{ key: 'action', label: 'Action' }, { key: 'outcome', label: 'Outcome' }, { key: 'user', label: 'User' },
        { key: 'srcIp', label: 'Source IP', mono: true }, { key: 'host', label: 'Host' }, { key: 'text', label: 'Message', wide: true }],
    logs: [{ key: 'service', label: 'Log' }, { key: 'endpoint', label: 'Endpoint' }, { key: 'text', label: 'Message', mono: true, wide: true }],
};

const BASE = '/api/security/soc/hunts';

const call = async <T,>(url: string, method = 'GET', body?: unknown): Promise<T> => {
    const res = await authFetch(url, method === 'GET' ? undefined : { method, body: body === undefined ? undefined : JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `HTTP ${res.status}`);
    return data as T;
};

export const fetchHuntFields = () => call<HuntCatalogue>(`${BASE}/fields`);
export const runHunt = (q: HuntQuery) => call<HuntResult>(`${BASE}/run?q=${encodeURIComponent(JSON.stringify(q))}`);
export const fetchHunts = () => call<HuntList>(BASE);
export const saveHunt = (body: { name: string; description?: string; query: HuntQuery }, id?: string) =>
    call<SavedHunt>(id ? `${BASE}/${encodeURIComponent(id)}` : BASE, id ? 'PUT' : 'POST', body);
export const deleteHunt = (id: string) => call<{ success: boolean }>(`${BASE}/${encodeURIComponent(id)}`, 'DELETE');
export const rerunHunt = (id: string) => call<HuntResult & { hunt: SavedHunt }>(`${BASE}/${encodeURIComponent(id)}/run`);
export const huntToRule = (id: string, draft: RuleDraft) =>
    call<{ id: string; name: string; mode: 'record' | 'alert'; logSource: string }>(`${BASE}/${encodeURIComponent(id)}/rule`, 'POST', draft);

/** The query as the server takes it: 'any of' split on commas, 'is present' as yes/no, unfinished filters dropped. */
export const toQuery = (d: HuntDraft): HuntQuery => ({
    source: d.source, text: d.text.trim(), range: d.range, countBy: d.countBy || null,
    filters: d.filters.filter(f => f.field && (f.op === 'exists' || f.op === 'eq' || f.value.trim())).map(f => ({
        field: f.field, op: f.op,
        value: f.op === 'in' ? f.value.split(',').map(v => v.trim()).filter(Boolean) : f.op === 'exists' ? f.value !== 'no' : f.value.trim(),
    })),
});

export const fromQuery = (q: HuntQuery): HuntDraft => ({
    source: q.source, text: q.text || '', range: q.range, countBy: q.countBy || null,
    filters: q.filters.map(f => ({
        field: f.field, op: f.op,
        value: Array.isArray(f.value) ? f.value.join(', ') : f.op === 'exists' ? (f.value ? 'yes' : 'no') : String(f.value ?? ''),
    })),
});

/** Same hunt whatever the server normalised (numbers for event ids, de-duplicated lists). */
export const sameQuery = (a: HuntQuery, b: HuntQuery): boolean => {
    const key = (q: HuntQuery) => JSON.stringify([q.source, q.text || '', q.range, q.countBy || null,
        q.filters.map(f => [f.field, f.op, Array.isArray(f.value) ? f.value.map(String) : String(f.value)])]);
    return key(a) === key(b);
};

/** Why this hunt cannot run as a SIEM rule (the server's rule_logic), or null when it can. */
export const ruleBlocker = (q: HuntQuery): string | null => {
    if (q.source !== 'events') return 'Only a hunt over SIEM events can become a rule.';
    if (q.text) return 'A rule matches fields, not free text: turn the text into a field filter.';
    const sources = q.filters.filter(f => f.field === 'source');
    if (sources.length !== 1 || sources[0].op !== 'eq') return "A rule runs on one log source: add exactly one 'Log source equals' filter.";
    const rest = q.filters.filter(f => f.field !== 'source');
    if (rest.some(f => f.op !== 'eq' && f.op !== 'in')) return "A rule can use only 'equals' and 'is any of' filters.";
    if (new Set(rest.map(f => f.field)).size !== rest.length) return 'A rule can filter each field only once.';
    if (!rest.length) return 'Add at least one filter besides the log source, so the rule does not fire on every event.';
    return null;
};

/** One line saying what a hunt looks for, in the catalogue's labels. */
export const describeHunt = (q: HuntQuery, cat: HuntCatalogue | null): string => {
    const info = cat?.sources[q.source];
    const label = (name: string) => info?.fields.find(f => f.name === name)?.label ?? name;
    const parts = q.filters.map(f => `${label(f.field)} ${OP_LABEL[f.op]}${f.op === 'exists' ? (f.value ? '' : ' (no)') : ` ${Array.isArray(f.value) ? f.value.join(', ') : f.value}`}`);
    if (q.text) parts.push(`text “${q.text}”`);
    const where = parts.length ? ` where ${parts.join(' and ')}` : '';
    return `${info?.label ?? q.source}${where}${q.countBy ? `, counted by ${label(q.countBy)}` : ''}, last ${RANGE_LABEL[q.range]}`;
};
