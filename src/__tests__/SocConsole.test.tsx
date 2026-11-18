/**
 * Security Operations Center console (Security Overview) and Alert Management on the shared alerts:
 *  1. The overview shows active alerts by severity, says response times are not measured until analysts
 *     act, writes the trend out in words, names removed endpoints and lists approved AI processes.
 *  2. Panels open the queue on a type or endpoint; the queue shows repeats and acknowledges in bulk.
 *  3. The drawer closes an alert with a resolution and approves an AI process for its endpoint.
 *  4. A pushed alert refreshes the overview; revoking an approval calls DELETE.
 *  5. Alert Management reads /api/alerts/queue; Dismiss closes as benign, Archive never deletes.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({
    API_BASE: '/api', authFetch: (...a: unknown[]) => authFetch(...a),
    togglePlaybook: vi.fn(), scanArtifactWithVirusTotal: vi.fn(),
}));
const socketHandlers: Record<string, (data: any) => void> = {};
vi.mock('../../services/socketService', () => ({
    socketService: { on: (ev: string, fn: (data: any) => void) => { socketHandlers[ev] = fn; }, off: vi.fn(), connected: true },
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { SecurityDashboard } from '../../components/SecurityDashboard';
import { AlertManagementDashboard } from '../../components/AlertManagementDashboard';
import { formatDuration } from '../../components/security/soc/socData';
import { UserContext } from '../../contexts/UserContext';
import { TimeZoneProvider } from '../../contexts/TimeZoneContext';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
const at = (hoursAgo: number) => new Date(Date.now() - hoursAgo * 3600_000).toISOString();
const zero = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };

const summary = () => ({
    generatedAt: at(0), range: '24h', rangeSeconds: 86400, bucketSeconds: 3600,
    kpis: {
        active: 3, open: 2, activeBySeverity: { ...zero, critical: 1, high: 1, medium: 1 }, newInRange: 2, newPrevious: 1,
        occurrencesInRange: 2, timeToAcknowledge: { seconds: null, count: 0 }, timeToClose: { seconds: null, count: 0 },
        endpointsWithActive: 2, removedWithActive: 1, endpointsOnline: 1, endpoints: 2,
    },
    trend: Array.from({ length: 24 }, (_, i) => ({ t: at(24 - i), ...zero, ...(i === 23 ? { critical: 1, high: 1 } : {}) })),
    byType: [{ type: 'runtime_security', label: 'Runtime threat', active: 1, inRange: 1, lastSeen: at(1) },
             { type: 'fim_violation', label: 'File integrity', active: 1, inRange: 1, lastSeen: at(1) }],
    endpoints: [
        { agentId: 'ag-srv', hostname: 'Omniai-copy', online: true, known: true, active: 2, ...zero, critical: 1, high: 1, lastAlertAt: at(1) },
        { agentId: 'agent-c6eb3d8bb3c0', hostname: 'agent-c6eb3d8bb3c0', online: false, known: false, active: 1, ...zero, medium: 1, lastAlertAt: at(30) },
    ],
    mitre: [{ technique: 'T1003.001', name: 'LSASS Memory', tactic: 'Credential Access', count: 1 }],
    sources: [{ type: 'runtime_security', label: 'Runtime threat', lastAlertAt: at(1), total: 1 },
              { type: 'malware_detected', label: 'Malware', lastAlertAt: null, total: 0 }],
    coverage: [{ check: 'fim', label: 'File integrity', agents: 2 }],
    counts: { openCases: 0, siemRules: 26, activeHunts: 19 },
});

const alert = (over: Record<string, unknown> = {}) => ({
    id: 'al-1', source: 'security', type: 'shadow_ai_process', typeLabel: 'Unapproved AI process', severity: 'medium',
    title: 'Unapproved AI process: lmstudio', description: "Local AI process 'lmstudio' (PID 7)", status: 'open', resolution: null,
    agentId: 'ag-srv', hostname: 'Omniai-copy', createdAt: at(30), lastSeenAt: at(1), occurrences: 12, mitre: [],
    evidence: { process: 'lmstudio', exe: '/opt/lmstudio' }, ...over,
});
const approval = { id: 'ap-1', process: 'ollama', agentId: 'ag-srv', hostname: 'Omniai-copy', reason: "The platform's own local LLM" };

const incident = () => ({ id: 'INC-1', agentId: 'ag-srv', hostname: 'Omniai-copy', title: 'Unapproved AI process: lmstudio and 2 more',
    severity: 'high', status: 'open', resolution: null, alertCount: 3, grouping: true, startedAt: at(2), lastAlertAt: at(1),
    tactics: ['Execution', 'Credential Access'], techniques: ['T1059', 'T1003'] });
let canRespond = true;
const responseInfo = () => ({
    host: 'Omniai-copy', isolated: false, canRespond,
    options: [
        { action: 'isolate_host', label: 'Isolate host', available: true, reason: null, target: { host: 'Omniai-copy' } },
        { action: 'quarantine_file', label: 'Quarantine file', available: false, reason: 'This kind of alert does not point at a harmful file.', target: { host: 'Omniai-copy' } },
        { action: 'block_ip', label: 'Block IP', available: true, reason: null, target: { host: 'Omniai-copy', ip: '45.33.32.156' } },
        { action: 'kill_process', label: 'End process', available: false, reason: 'The alert does not name the process id, start time and program.', target: { host: 'Omniai-copy' } },
    ],
    history: [{ actionId: 'AO-0', action: 'isolate_host', label: 'Isolate host', state: 'executed', stateText: 'Done', requestedBy: 'Ava',
                createdAt: at(1), revertsAt: at(-3), keptIsolated: false, canUndo: true, canKeepIsolated: true }],
});

function route(url: string, init?: RequestInit) {
    const u = new URL(url, 'http://x');
    if (u.pathname === '/api/security/soc/summary') return ok(summary());
    if (u.pathname === '/api/security/soc/approved-ai' && !init?.method) return ok({ items: [approval] });
    if (u.pathname === '/api/security/soc/alerts' && !init?.method) return ok({ items: [alert()], total: 1, limit: 50, offset: 0 });
    if (u.pathname === '/api/alerts/queue' && !init?.method) {
        return ok({ items: [alert(), alert({ id: 'al-2', severity: 'info', title: 'Login at 05:00', type: 'ueba_anomaly', typeLabel: 'Unusual user behaviour', status: 'closed', resolution: 'benign' })], total: 2, limit: 500, offset: 0 });
    }
    if (u.pathname.endsWith('/response') && !init?.method) return ok(responseInfo());
    if (u.pathname.endsWith('/respond')) return ok({ actionId: 'AO-1', status: 'dispatched' });
    if (u.pathname.endsWith('/context') && !init?.method) return ok({ risk: 76, user: null, indicators: { ip: '45.33.32.156' },
        threatIntel: [{ value: '45.33.32.156', kind: 'ip', source: 'feodo', malware: 'botnet C2' }],
        feeds: { indicators: 1, feeds: [{ source: 'feodo', ok: true, count: 1, at: at(1) }, { source: 'threatfox', ok: false, needsKey: true }] },
        host: { agentId: 'ag-srv', enrolled: true, hostname: 'Omniai-copy', os: 'Linux', importance: 'medium', owner: null, otherActiveAlerts: 2 } });
    if (u.pathname.includes('/endpoints/') && init?.method === 'PUT') return ok({ importance: 'critical', owner: 'IT desk' });
    if (u.pathname === '/api/security/soc/rules' && !init?.method) return ok({ items: [], canEdit: true });
    if (u.pathname === '/api/security/soc/rules/preview') return ok({ days: 7, checked: 40, matched: 35, examples: [{ id: 'x', title: 'UEBA Anomaly: Unusual Login Time' }] });
    if (u.pathname === '/api/security/soc/incidents') return ok({ items: [incident()], total: 1, limit: 50, offset: 0 });
    if (u.pathname === '/api/security/soc/incidents/INC-1') return ok({ ...incident(), timeline: [alert()], ...(init?.method === 'PATCH' ? { status: 'closed', resolution: 'benign' } : {}) });
    if (u.pathname.endsWith('/triage')) return ok({ summary: 'A local AI tool runs on purpose.', likelyCause: 'Developer tooling.', seriousness: 'low',
        why: 'Known program.', nextSteps: ['approve_process', 'close_benign'], model: 'llama3.2:3b', at: at(0), by: 'ava@x.test' });
    if (u.pathname.endsWith('/bulk')) return ok({ matched: 1, modified: 1 });
    if (u.pathname.endsWith('/approve')) return ok({ approval: { ...approval, id: 'ap-2', process: 'lmstudio' }, closed: 1 });
    if (init?.method === 'PATCH') return ok(alert({ ...JSON.parse(String(init.body)), status: 'closed', resolution: 'false_positive' }));
    return ok({ success: true });
}

const calls = (method: string, path: string) =>
    authFetch.mock.calls.filter(([url, init]) => (init?.method ?? 'GET') === method && String(url).startsWith(path));

function renderConsole() {
    const user = { id: 'u', name: 'Ava', email: 'ava@x.test', role: 'Tenant Admin', tenantId: 't' } as any;
    return render(
        <TimeZoneProvider>
            <UserContext.Provider value={{ currentUser: user, hasPermission: () => true } as any}>
                <SecurityDashboard securityCases={[]} playbooks={[]} securityEvents={[]} users={[]} onCaseUpdate={vi.fn(async c => c)}
                    onGeneratePlaybook={vi.fn()} onAnalyzeImpact={vi.fn()} threatIntelFeed={[]} />
            </UserContext.Provider>
        </TimeZoneProvider>,
    );
}

beforeEach(() => { canRespond = true; authFetch.mockReset(); authFetch.mockImplementation(async (url: string, init?: RequestInit) => route(url, init)); });

describe('socData', () => {
    it('writes response times the way analysts read them', () => {
        expect(formatDuration(null)).toBe('—');
        expect(formatDuration(45)).toBe('45 s');
        expect(formatDuration(11_400)).toBe('3 h 10 min');
        expect(formatDuration(3 * 86400 + 4 * 3600)).toBe('3 d 4 h');
    });
});

describe('Security Operations Center overview', () => {
    it('shows the live picture and says what is not measured yet', async () => {
        renderConsole();
        expect(await screen.findByRole('heading', { level: 1, name: 'Security Operations Center' })).toBeTruthy();
        const active = (await screen.findByRole('heading', { name: 'Active alerts' })).closest('section')!;
        expect(within(active).getByText('3')).toBeTruthy();
        expect(within(active).getByText('2 open · 1 acknowledged')).toBeTruthy();
        expect(screen.getByText('Not measured')).toBeTruthy();
        expect(screen.getByText(/2 new alerts: 1 critical, 1 high\./)).toBeTruthy();
        expect(screen.getByText('Removed endpoint (c6eb3d8b)')).toBeTruthy();
        expect(screen.getByText('1 removed endpoint still has alerts')).toBeTruthy();
        expect(screen.getByRole('link', { name: /T1003\.001/ }).getAttribute('href')).toBe('https://attack.mitre.org/techniques/T1003/001/');
        expect(screen.getByText('ollama')).toBeTruthy();
        expect(screen.getByText(/26 SIEM correlation rules/)).toBeTruthy();
        expect(screen.getByRole('button', { name: /Alert queue/ }).textContent).toContain('3');
    });

    it('a pushed alert refreshes the overview, and the range picker reloads', async () => {
        renderConsole();
        await screen.findByRole('heading', { name: 'Active alerts' });
        const before = calls('GET', '/api/security/soc/summary').length;
        act(() => socketHandlers.security_alert?.({ id: 'x', severity: 'high' }));
        await waitFor(() => expect(calls('GET', '/api/security/soc/summary').length).toBe(before + 1));
        fireEvent.click(screen.getByRole('button', { name: '7d' }));
        await waitFor(() => expect(calls('GET', '/api/security/soc/summary?range=7d').length).toBe(1));
    });

    it('removing an approval asks the server to stop approving the process', async () => {
        renderConsole();
        fireEvent.click(await screen.findByRole('button', { name: 'Stop approving ollama on Omniai-copy' }));
        await waitFor(() => expect(calls('DELETE', '/api/security/soc/approved-ai/ap-1').length).toBe(1));
    });
});

describe('Alert queue and drawer', () => {
    it('an endpoint opens the queue on that endpoint; repeats show and bulk acknowledge posts the ids', async () => {
        renderConsole();
        fireEvent.click(await screen.findByRole('button', { name: /^Omniai-copy/ }));
        await waitFor(() => expect(calls('GET', '/api/security/soc/alerts').some(([u]) => String(u).includes('agentId=ag-srv'))).toBe(true));
        const row = (await screen.findByRole('button', { name: 'Unapproved AI process: lmstudio' })).closest('tr')!;
        expect(row.textContent).toContain('seen 12 times');
        expect(row.textContent).toContain('Omniai-copy');
        fireEvent.click(screen.getByRole('checkbox', { name: 'Select Unapproved AI process: lmstudio' }));
        fireEvent.click(screen.getByRole('button', { name: 'Acknowledge' }));
        await waitFor(() => expect(calls('POST', '/api/security/soc/alerts/bulk').length).toBe(1));
        expect(JSON.parse(String(calls('POST', '/api/security/soc/alerts/bulk')[0][1].body))).toEqual({ ids: ['al-1'], action: 'acknowledge' });
    });

    it('closes an alert with a resolution and note, and approves an AI process on its endpoint', async () => {
        renderConsole();
        fireEvent.click(await screen.findByRole('button', { name: /Alert queue/ }));
        fireEvent.click(await screen.findByRole('button', { name: 'Unapproved AI process: lmstudio' }));
        const drawer = screen.getByRole('dialog');
        fireEvent.click(within(drawer).getByRole('radio', { name: /False positive/ }));
        fireEvent.change(within(drawer).getByRole('textbox', { name: /Note/ }), { target: { value: 'IT test box' } });
        fireEvent.click(within(drawer).getByRole('button', { name: 'Close as false positive' }));
        await waitFor(() => expect(calls('PATCH', '/api/security/soc/alerts/al-1').length).toBe(1));
        expect(JSON.parse(String(calls('PATCH', '/api/security/soc/alerts/al-1')[0][1].body)))
            .toEqual({ action: 'close', resolution: 'false_positive', note: 'IT test box' });
    });

    it('approving sends the endpoint-only scope by default', async () => {
        renderConsole();
        fireEvent.click(await screen.findByRole('button', { name: /Alert queue/ }));
        fireEvent.click(await screen.findByRole('button', { name: 'Unapproved AI process: lmstudio' }));
        fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve lmstudio' }));
        await waitFor(() => expect(calls('POST', '/api/security/soc/alerts/al-1/approve').length).toBe(1));
        expect(JSON.parse(String(calls('POST', '/api/security/soc/alerts/al-1/approve')[0][1].body))).toEqual({ allEndpoints: false });
    });
});

describe('One-click response', () => {
    const openDrawer = async () => {
        renderConsole();
        fireEvent.click(await screen.findByRole('button', { name: /Alert queue/ }));
        fireEvent.click(await screen.findByRole('button', { name: 'Unapproved AI process: lmstudio' }));
        return screen.getByRole('dialog');
    };

    it('says why an action is unavailable and confirms before blocking for the chosen time', async () => {
        const drawer = await openDrawer();
        expect(await within(drawer).findByText('This kind of alert does not point at a harmful file.')).toBeTruthy();
        expect(within(drawer).getByRole('button', { name: 'Quarantine file' })).toBeDisabled();
        fireEvent.change(within(drawer).getByLabelText('Block for'), { target: { value: '1h' } });
        fireEvent.click(within(drawer).getByRole('button', { name: 'Block IP' }));
        expect(within(drawer).getByText(/Blocks traffic between Omniai-copy and 45\.33\.32\.156 for 1 hour/)).toBeTruthy();
        expect(calls('POST', '/api/security/soc/alerts/al-1/respond').length).toBe(0);
        fireEvent.click(within(drawer).getByRole('button', { name: 'Confirm: block ip' }));
        await waitFor(() => expect(calls('POST', '/api/security/soc/alerts/al-1/respond').length).toBe(1));
        expect(JSON.parse(String(calls('POST', '/api/security/soc/alerts/al-1/respond')[0][1].body))).toEqual({ action: 'block_ip', ttl: '1h' });
    });

    it('lists what was done with Undo and Keep isolated', async () => {
        const drawer = await openDrawer();
        fireEvent.click(await within(drawer).findByRole('button', { name: 'Keep isolated' }));
        await waitFor(() => expect(calls('POST', '/api/security/soc/alerts/al-1/response/AO-0/keep-isolated').length).toBe(1));
        fireEvent.click(within(drawer).getByRole('button', { name: 'Undo' }));
        await waitFor(() => expect(calls('POST', '/api/security/soc/alerts/al-1/response/AO-0/undo').length).toBe(1));
    });

    it('without the Active Response permission nothing can be sent', async () => {
        canRespond = false;
        const drawer = await openDrawer();
        expect(await within(drawer).findByText('Acting on endpoints needs the Active Response permission.')).toBeTruthy();
        expect(within(drawer).getByRole('button', { name: 'Isolate host' })).toBeDisabled();
        expect(within(drawer).queryByRole('button', { name: 'Undo' })).toBeNull();
    });
});

describe('Incidents', () => {
    it('lists incidents with their attack stages and closes one together with its open alerts', async () => {
        renderConsole();
        fireEvent.click(await screen.findByRole('button', { name: /^Incidents/ }));
        const row = await screen.findByRole('button', { name: /Unapproved AI process: lmstudio and 2 more/ });
        expect(within(row).getByRole('list', { name: 'Attack stages in order' }).textContent).toBe('ExecutionCredential Access');
        fireEvent.click(row);
        const drawer = await screen.findByRole('dialog', { name: /Unapproved AI process: lmstudio and 2 more/ });
        expect(await within(drawer).findByText(/still collecting/)).toBeTruthy();
        fireEvent.click(within(drawer).getByRole('radio', { name: 'Benign' }));
        expect(within(drawer).getByRole('checkbox', { name: /Also close its 1 open alert/ })).toBeChecked();
        fireEvent.click(within(drawer).getByRole('button', { name: 'Close incident as benign' }));
        await waitFor(() => expect(calls('PATCH', '/api/security/soc/incidents/INC-1').length).toBe(1));
        expect(JSON.parse(String(calls('PATCH', '/api/security/soc/incidents/INC-1')[0][1].body))).toEqual({ action: 'close', resolution: 'benign', closeAlerts: true });
    });
});

describe('Automation rules', () => {
    it('builds a rule in words, previews it on the last week and saves it', async () => {
        renderConsole();
        fireEvent.click(await screen.findByRole('button', { name: /Automation/ }));
        fireEvent.click(await screen.findByRole('button', { name: 'New rule' }));
        fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Night logins' } });
        fireEvent.click(screen.getByRole('checkbox', { name: 'Runtime threat' }));
        fireEvent.change(screen.getByLabelText('Close as'), { target: { value: 'benign' } });
        expect(screen.getByText('When Runtime threat, close as benign.')).toBeTruthy();
        fireEvent.click(screen.getByRole('button', { name: 'Preview on the last 7 days' }));
        expect(await screen.findByText(/Would have matched/)).toBeTruthy();
        fireEvent.click(screen.getByRole('button', { name: 'Save rule' }));
        await waitFor(() => expect(calls('POST', '/api/security/soc/rules').filter(([u]) => !String(u).includes('preview')).length).toBe(1));
        const body = JSON.parse(String(calls('POST', '/api/security/soc/rules').find(([u]) => !String(u).includes('preview'))![1].body));
        expect(body.conditions.types).toEqual(['runtime_security']);
        expect(body.actions.close).toBe('benign');
    });
});

describe('Enrichment and risk', () => {
    it('sorts the queue by risk and lets the endpoint importance and owner be set from the alert', async () => {
        renderConsole();
        fireEvent.click(await screen.findByRole('button', { name: /Alert queue/ }));
        fireEvent.change(await screen.findByLabelText('Sort by'), { target: { value: 'risk' } });
        await waitFor(() => expect(calls('GET', '/api/security/soc/alerts').some(([u]) => String(u).includes('sort=risk'))).toBe(true));
        fireEvent.click(await screen.findByRole('button', { name: 'Unapproved AI process: lmstudio' }));
        const drawer = screen.getByRole('dialog');
        expect(await within(drawer).findByText('76')).toBeTruthy();
        expect(within(drawer).getByText(/is listed by Feodo Tracker/)).toBeTruthy();
        expect(within(drawer).getByText(/ThreatFox \(IPs, domains, hashes\) needs a free abuse\.ch key/)).toBeTruthy();
        fireEvent.change(within(drawer).getByLabelText('Importance'), { target: { value: 'critical' } });
        fireEvent.change(within(drawer).getByLabelText('Owner'), { target: { value: 'IT desk' } });
        fireEvent.click(within(drawer).getByRole('button', { name: 'Save' }));
        await waitFor(() => expect(calls('PUT', '/api/security/soc/endpoints/ag-srv/context').length).toBe(1));
        expect(JSON.parse(String(calls('PUT', '/api/security/soc/endpoints/ag-srv/context')[0][1].body))).toEqual({ importance: 'critical', owner: 'IT desk' });
    });
});

describe('AI triage', () => {
    it('explains on request, labels it as a suggestion, and a step only points at the control', async () => {
        renderConsole();
        fireEvent.click(await screen.findByRole('button', { name: /Alert queue/ }));
        fireEvent.click(await screen.findByRole('button', { name: 'Unapproved AI process: lmstudio' }));
        const drawer = screen.getByRole('dialog');
        fireEvent.click(within(drawer).getByRole('button', { name: 'Explain this alert' }));
        expect(await within(drawer).findByText('A local AI tool runs on purpose.')).toBeTruthy();
        expect(within(drawer).getByText(/AI suggestion: check it before acting\. llama3\.2:3b on this server/)).toBeTruthy();
        const before = authFetch.mock.calls.length;
        fireEvent.click(within(drawer).getByRole('button', { name: 'Close as benign' }));
        expect(within(drawer).getByRole('radio', { name: /Benign/ })).toBeChecked();
        expect(authFetch.mock.calls.length).toBe(before);
    });
});

describe('Alert Management on the shared alerts', () => {
    it('lists the queue, dismisses as benign and archives instead of deleting', async () => {
        const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
        render(<AlertManagementDashboard />);
        expect(await screen.findByText('Unapproved AI process: lmstudio')).toBeTruthy();
        expect(calls('GET', '/api/alerts/queue').length).toBe(1);
        expect(within(screen.getByRole('table')).getByText('Closed')).toBeTruthy();
        fireEvent.click(screen.getAllByRole('checkbox')[1]);
        fireEvent.click(screen.getByRole('button', { name: /Dismiss/ }));
        await waitFor(() => expect(calls('POST', '/api/alerts/queue/bulk').length).toBe(1));
        expect(JSON.parse(String(calls('POST', '/api/alerts/queue/bulk')[0][1].body))).toEqual({ ids: ['al-1'], action: 'close', resolution: 'benign' });
        fireEvent.click(screen.getAllByRole('checkbox')[1]);
        fireEvent.click(screen.getByRole('button', { name: /Archive/ }));
        await waitFor(() => expect(calls('POST', '/api/alerts/queue/bulk').length).toBe(2));
        expect(JSON.parse(String(calls('POST', '/api/alerts/queue/bulk')[1][1].body))).toEqual({ ids: ['al-1'], action: 'archive' });
        expect(confirm.mock.calls[0][0]).toMatch(/nothing is deleted/);
        confirm.mockRestore();
    });
});
