/**
 * SOC console, Hunting: a structured query over SOC alerts, SIEM events or agent logs runs as GET with the query as
 * JSON; groups drill down into a filter; saved hunts rerun with their count; only the latest answer is shown; a saved
 * exact hunt over SIEM events becomes a SIEM rule, and the panel says why when a hunt cannot.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: (...a: unknown[]) => authFetch(...a) }));
const showToast = vi.fn();
vi.mock('../../utils/toast', () => ({ showToast: (...a: unknown[]) => showToast(...a) }));

import { HuntTab } from '../../components/security/soc/HuntTab';
import { ruleBlocker, toQuery, fromQuery, sameQuery, type HuntQuery } from '../../components/security/soc/huntData';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
const bad = (status: number, detail: string) => ({ ok: false, status, json: async () => ({ detail }) });
const calls = (method: string, path: string) =>
    authFetch.mock.calls.filter(([url, init]) => (init?.method ?? 'GET') === method && String(url).startsWith(path));
const queryOf = (url: string) => JSON.parse(decodeURIComponent(String(url).split('?q=')[1]));

const f = (name: string, label: string, values: (string | number)[] = []) => ({ name, label, values, ruleable: true });
const catalogue = {
    sources: {
        events: { label: 'SIEM events', text: 'message', fields: [f('source', 'Log source', ['linux_auth']), f('action', 'Action', ['login_failed', 'sudo_command']),
            f('srcIp', 'Source IP', ['2.57.121.25']), f('user', 'User')] },
        alerts: { label: 'SOC alerts', text: 'title and description', fields: [f('severity', 'Severity', ['high']), f('title', 'Title')] },
        logs: { label: 'Agent logs', text: 'message', fields: [f('service', 'Log', ['syslog', 'auth'])] },
    },
    ranges: ['1h', '24h', '7d', '30d', '90d'],
};
const FAILED: HuntQuery = { source: 'events', text: '', range: '24h', countBy: 'srcIp',
    filters: [{ field: 'source', op: 'eq', value: 'linux_auth' }, { field: 'action', op: 'eq', value: 'login_failed' }] };
const saved = { id: 'hunt-1', name: 'SSH failures by address', query: FAILED, runCount: 2, lastRunAt: '2026-11-18T15:00:00Z', lastCount: 4, ruleId: null };
const result = (q: HuntQuery, total: number, extra: Record<string, unknown> = {}) => ({
    query: q, total, groupCount: 2, since: '2026-11-17T16:00:00Z', until: '2026-11-18T16:00:00Z', tookMs: 6,
    groups: q.countBy ? [{ value: '2.57.121.25', count: 4 }, { value: '35.187.231.181', count: 1 }] : [],
    rows: [{ time: '2026-11-18T15:59:00Z', action: 'login_failed', outcome: 'failure', user: 'admin', srcIp: '2.57.121.25', host: 'Omniai-copy',
        text: 'Invalid user admin from 2.57.121.25 port 13712' }], ...extra,
});

let list = { items: [saved], canEdit: true, canMakeRules: true };
const routes = async (url: string, init?: { method?: string; body?: string }) => {
    const u = String(url), method = init?.method ?? 'GET';
    if (u === '/api/security/soc/hunts/fields') return ok(catalogue);
    if (u === '/api/security/soc/hunts' && method === 'GET') return ok(list);
    if (u.startsWith('/api/security/soc/hunts/run?q=')) return ok(result(queryOf(u), 5));
    if (u === '/api/security/soc/hunts/hunt-1/run') return ok({ ...result(FAILED, 5), hunt: { ...saved, runCount: 3, lastCount: 5, lastRunAt: new Date().toISOString() } });
    if (u === '/api/security/soc/hunts' && method === 'POST') return ok({ ...JSON.parse(init!.body!), id: 'hunt-2' });
    if (u === '/api/security/soc/hunts/hunt-1/rule') return ok({ id: 'hunt-rule-1', name: 'SSH failures by address', mode: 'record', logSource: 'linux_auth' });
    return bad(404, `unexpected ${method} ${u}`);
};

beforeEach(() => {
    authFetch.mockReset(); showToast.mockReset();
    list = { items: [saved], canEdit: true, canMakeRules: true };
    authFetch.mockImplementation(routes);
});

describe('Hunting', () => {
    it('runs a built query as GET JSON and drills from a group into a filter', async () => {
        render(<HuntTab />);
        fireEvent.click(await screen.findByRole('button', { name: 'Add filter' }));
        fireEvent.change(screen.getByRole('combobox', { name: 'Filter 1 field' }), { target: { value: 'action' } });
        fireEvent.change(screen.getByRole('combobox', { name: 'Filter 1 value' }), { target: { value: 'login_failed' } });
        fireEvent.change(screen.getByRole('combobox', { name: 'Count by' }), { target: { value: 'srcIp' } });
        expect(screen.getByText('SIEM events where Action equals login_failed, counted by Source IP, last 24 hours.')).toBeTruthy();
        fireEvent.click(screen.getByRole('button', { name: 'Run hunt' }));

        expect(await screen.findByText(/in the last 24 hours/)).toBeTruthy();
        expect(screen.getByRole('status').textContent).toContain('5 matches');
        const [url] = calls('GET', '/api/security/soc/hunts/run')[0];
        expect(queryOf(url)).toEqual({ source: 'events', text: '', range: '24h', countBy: 'srcIp', filters: [{ field: 'action', op: 'eq', value: 'login_failed' }] });
        expect(screen.getByRole('cell', { name: 'Invalid user admin from 2.57.121.25 port 13712' })).toBeTruthy();

        fireEvent.click(within(screen.getByRole('region', { name: 'Counted by Source IP' })).getByRole('button', { name: 'Filter to Source IP 35.187.231.181' }));
        await waitFor(() => expect(calls('GET', '/api/security/soc/hunts/run')).toHaveLength(2));
        const drilled = queryOf(calls('GET', '/api/security/soc/hunts/run')[1][0]);
        expect(drilled.countBy).toBeNull();
        expect(drilled.filters).toContainEqual({ field: 'srcIp', op: 'eq', value: '35.187.231.181' });
    });

    it('reruns a saved hunt with its count and shows only the latest answer', async () => {
        let release: (v: unknown) => void = () => {};
        authFetch.mockImplementation(async (url: string, init?: { method?: string }) =>
            (String(url).startsWith('/api/security/soc/hunts/run?q=') && calls('GET', '/api/security/soc/hunts/run').length === 1
                ? new Promise(r => { release = r; }) : routes(url, init)));
        render(<HuntTab />);
        fireEvent.click(await screen.findByRole('button', { name: 'Run hunt' }));  // slow, superseded
        fireEvent.click(screen.getByRole('button', { name: 'Run saved hunt SSH failures by address' }));
        expect(await screen.findByText('5 matches, run just now', { exact: false })).toBeTruthy();
        release(ok(result(FAILED, 999)));
        await waitFor(() => expect(screen.getByRole('status').textContent).toContain('5 matches'));
        expect(screen.getByRole('status').textContent).not.toContain('999');
        expect(screen.getByText(/Saved hunt:/).textContent).toContain('SSH failures by address');
    });

    it('saves a hunt and turns the saved one into a rule that records first', async () => {
        render(<HuntTab />);
        fireEvent.click(await screen.findByRole('button', { name: 'Run saved hunt SSH failures by address' }));
        await screen.findByText(/Saved hunt:/);
        fireEvent.click(screen.getByRole('button', { name: /Make a rule/ }));
        const panel = screen.getByRole('region', { name: 'Make a SIEM rule' });
        expect(within(panel).getByText(/5 or more matching events share one Source IP within 10 minutes/)).toBeTruthy();
        fireEvent.change(within(panel).getByRole('spinbutton', { name: 'At least' }), { target: { value: '10' } });
        fireEvent.click(within(panel).getByRole('button', { name: 'Create rule' }));
        await waitFor(() => expect(calls('POST', '/api/security/soc/hunts/hunt-1/rule')).toHaveLength(1));
        expect(JSON.parse(calls('POST', '/api/security/soc/hunts/hunt-1/rule')[0][1].body))
            .toEqual({ name: 'SSH failures by address', severity: 'Medium', count: 10, windowMinutes: 10, alertNow: false });
        await waitFor(() => expect(showToast).toHaveBeenCalledWith(expect.stringContaining('records hits for 7 days'), 'success'));
        expect(screen.getByText(/Has a SIEM rule \(hunt-rule-1\)/)).toBeTruthy();

        fireEvent.click(screen.getByRole('button', { name: 'New hunt' }));
        fireEvent.change(screen.getByRole('textbox', { name: 'Text in message' }), { target: { value: 'Invalid user' } });
        fireEvent.click(screen.getByRole('button', { name: 'Save hunt…' }));
        fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'Invalid users' } });
        fireEvent.click(screen.getByRole('button', { name: 'Save' }));
        const saves = () => calls('POST', '/api/security/soc/hunts').filter(([url]) => url === '/api/security/soc/hunts');
        await waitFor(() => expect(saves()).toHaveLength(1));
        expect(JSON.parse(saves()[0][1].body).query.text).toBe('Invalid user');
    });

    it('hides saving and deleting from someone who can only read', async () => {
        list = { items: [saved], canEdit: false, canMakeRules: false };
        render(<HuntTab />);
        await screen.findByRole('button', { name: 'Run saved hunt SSH failures by address' });
        expect(screen.queryByRole('button', { name: /Save hunt/ })).toBeNull();
        expect(screen.queryByRole('button', { name: /Delete saved hunt/ })).toBeNull();
    });

    it('says why a hunt cannot be a rule, as the server does', () => {
        expect(ruleBlocker(FAILED)).toBeNull();
        expect(ruleBlocker({ ...FAILED, source: 'alerts' })).toMatch(/SIEM events/);
        expect(ruleBlocker({ ...FAILED, text: 'admin' })).toMatch(/free text/);
        expect(ruleBlocker({ ...FAILED, filters: FAILED.filters.slice(1) })).toMatch(/one log source/);
        expect(ruleBlocker({ ...FAILED, filters: [...FAILED.filters, { field: 'user', op: 'contains', value: 'adm' }] })).toMatch(/only 'equals'/);
        const draft = fromQuery({ ...FAILED, filters: [...FAILED.filters, { field: 'eventId', op: 'in', value: [4625, 4740] }] });
        expect(draft.filters[2].value).toBe('4625, 4740');
        expect(sameQuery(toQuery(draft), { ...FAILED, filters: [...FAILED.filters, { field: 'eventId', op: 'in', value: [4625, 4740] }] })).toBe(true);
    });
});
